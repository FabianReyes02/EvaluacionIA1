"""Orquestacion del agente (Requisito A y C).

Flujo de cada interaccion:

    contexto (catalogo + memoria largo plazo + resumen de sesion)
        -> el LLM elige una o mas tools (plan)
        -> observa el resultado
        -> responde
        -> guardrails re-verifican codigos y stock contra el CSV
        -> se guarda la traza en logs/trace.jsonl
        -> se actualiza la memoria de corto plazo

Si no hay API key o la llamada falla, cae a una busqueda directa sobre el CSV
sin IA, para que la interfaz siga siendo util igual que la CLI.
"""
from __future__ import annotations

import os
import re
import threading
import time

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, SystemMessage

from agent.guardrails import apply as apply_guardrails
from agent.llm_client import (
    RATE_LIMIT_RETRIES,
    daily_limit_reset_hint,
    get_chat_model,
    get_provider_config,
    is_daily_limit_error,
    is_rate_limit_error,
    retry_delay_s,
    usage_from,
)
from agent.memory import LongTermMemory, get_session, liberar_usuario, usar_usuario
from agent.prompts import SYSTEM_PROMPT, build_context_block
from agent.tools import (
    ALL_TOOLS,
    correo_de_sesion,
    get_inventory,
    liberar_correo_sesion,
    liberar_id_sesion,
    usar_correo_sesion,
    usar_id_sesion,
)
from agent.trace import log_trace, steps_from_messages
from tools.email_sender import get_email_config
from tools.inventory_lookup import (
    diagnose_missing,
    find_by_code,
    format_part,
    get_catalog_summary,
    search_parts,
)

_agent = None
_agent_model_id = None
_AGENT_LOCK = threading.RLock()

# Circuit breaker: tras varios 429 seguidos se deja de llamar al proveedor
# durante unos segundos. El servidor web devuelve 503 en vez de acumular hilos.
_CIRCUIT = {"fallos": 0, "abierto_hasta": 0.0}
_CIRCUIT_LOCK = threading.Lock()
CIRCUIT_THRESHOLD = max(1, int(os.getenv("AGENT_CIRCUIT_THRESHOLD") or 3))
CIRCUIT_COOLDOWN_S = max(5, int(os.getenv("AGENT_CIRCUIT_COOLDOWN_S") or 30))


def build_agent():
    """Compila el agente de LangChain (singleton por modelo, seguro con hilos)."""
    global _agent, _agent_model_id
    if _agent is not None:
        cfg = get_provider_config()
        if cfg is None or _agent_model_id == cfg["model"]:
            return _agent
    with _AGENT_LOCK:
        cfg = get_provider_config()
        if cfg is None:
            return None
        if _agent is not None and _agent_model_id == cfg["model"]:
            return _agent
        # Temperatura baja para el loop de herramientas: la seleccion de tools debe
        # ser estable (la prosa la suaviza el propio system prompt).
        model = get_chat_model(temperature=0.1)
        _agent = create_agent(model=model, tools=ALL_TOOLS, system_prompt=SYSTEM_PROMPT)
        _agent_model_id = cfg["model"]
    return _agent


def circuit_abierto() -> bool:
    """True si el proveedor esta temporalmente cortado por 429."""
    with _CIRCUIT_LOCK:
        return time.time() < _CIRCUIT["abierto_hasta"]


def circuit_reintentar_en() -> int:
    with _CIRCUIT_LOCK:
        return max(0, int(_CIRCUIT["abierto_hasta"] - time.time()))


def registrar_resultado(rate_limited: bool, limite_diario: bool = False) -> None:
    """Actualiza el circuit breaker con el resultado de una llamada."""
    with _CIRCUIT_LOCK:
        if limite_diario:
            _CIRCUIT["fallos"] = 0
            _CIRCUIT["abierto_hasta"] = 0.0
        elif rate_limited:
            _CIRCUIT["fallos"] += 1
            if _CIRCUIT["fallos"] >= CIRCUIT_THRESHOLD:
                _CIRCUIT["abierto_hasta"] = time.time() + CIRCUIT_COOLDOWN_S
                print(f"(aviso) Circuit breaker abierto {CIRCUIT_COOLDOWN_S}s por 429 repetidos.")
        else:
            _CIRCUIT["fallos"] = 0


def _messages_for(agent_input: str, session_id: str) -> list:
    """Bloque de contexto + historial de corto plazo + mensaje nuevo."""
    inventory = get_inventory()
    context = build_context_block(
        catalog=get_catalog_summary(inventory),
        memoria=LongTermMemory.recent_context(),
        historial=get_session(session_id).summary(),
    )
    correo = correo_de_sesion()
    if correo:
        context += (
            f"\n\nCorreo electrónico del cliente autenticado: {correo}. "
            "Cuando pida enviar la cotización, usa esa dirección como destinatario "
            "sin pedírsela ni inventar otra."
        )
    history = get_session(session_id).as_messages()
    return [SystemMessage(content=context), *history, HumanMessage(content=agent_input)]


def _sum_tokens(messages) -> dict | None:
    total = {"prompt": 0, "completion": 0, "total": 0}
    found = False
    for msg in messages:
        usage = usage_from(msg)
        if usage:
            found = True
            for k in total:
                total[k] += usage[k]
    return total if found else None


def _invoke_with_retry(
    agent, payload: dict, max_wait_s: float | None = None
) -> tuple[dict, int, bool]:
    """Invoca el loop plan->tool con reintentos solo ante limite de tasa.

    ``max_wait_s`` permite a la web limitar el tiempo total dormido (para no
    acumular hilos); los evals lo dejan en None y mantienen el backoff completo.
    """
    intentos = max(0, RATE_LIMIT_RETRIES)
    esperado = 0.0
    for intento in range(intentos + 1):
        try:
            return agent.invoke(payload), intento, False
        except Exception as exc:
            if is_daily_limit_error(exc):
                print(f"(aviso) Limite diario de tokens del proveedor "
                      f"({exc.__class__.__name__}): no se reintenta.")
                raise
            if is_rate_limit_error(exc) and intento < intentos:
                espera = retry_delay_s(intento)
                if max_wait_s is not None and esperado + espera > max_wait_s:
                    raise  # el caller cae al fallback sin seguir durmiendo
                print(f"(aviso) Limite de tasa en el agente ({exc.__class__.__name__}): "
                      f"reintento {intento + 1}/{intentos} en {espera:.0f}s...")
                time.sleep(espera)
                esperado += espera
                continue
            raise
    raise RuntimeError("reintentos agotados")  # inalcanzable, por completitud


def _rate_limit_message() -> str:
    """Mensaje amable cuando se agotan los reintentos por limite de tasa."""
    return (
        "El servicio de IA esta saturado por limite de tasa (plan gratuito Groq, "
        "1000 tokens de salida/minuto). Reintente en un minuto; "
        "mientras tanto puedo buscar directo en el inventario. "
    )


def _daily_limit_message(exc: Exception) -> str:
    """Mensaje amable cuando se agota la cuota DIARIA de tokens (TPD)."""
    espera = daily_limit_reset_hint(exc)
    cuando = f" La cuota se reinicia en {espera}." if espera else ""
    return (
        "Se agoto la cuota diaria de tokens del proveedor (limite diario, no "
        f"por minuto).{cuando} Reintenta mas tarde; mientras tanto puedo "
        "buscar directo en el inventario. "
    )


def _fallback(user_input: str) -> str:
    """Busqueda directa sobre el CSV cuando no se puede usar el LLM."""
    inventory = get_inventory()
    text = user_input or ""

    # Si menciona un codigo, responde con esa fila.
    for code in re.findall(r"\b[A-Za-z]{2,4}-\d{2,3}\b", text):
        item = find_by_code(inventory, code)
        if item:
            return f"Repuesto {code} en inventario:\n- {format_part(item)}"

    # Sino, intenta armar marca/modelo/anio con lo que hay en el catalogo.
    anio = re.search(r"\b(?:19|20)\d{2}\b", text)
    marca = next(
        (m for m in {"Suzuki", "Hyundai", "Chevrolet", "Kia", "Toyota", "Bosch"} if m.lower() in text.lower()),
        "",
    )
    modelo = ""
    if marca:
        for item in inventory:
            for chunk in item["vehiculos_compatibles"].split(";"):
                if marca.lower() in chunk.lower():
                    palabras = [p for p in chunk.replace(";", " ").split() if p.lower() != marca.lower()]
                    for p in palabras:
                        if p.isalpha() and len(p) > 3 and p.lower() in text.lower():
                            modelo = p
                            break
                if modelo:
                    break
            if modelo:
                break

    if marca and modelo and anio:
        results = search_parts(inventory, marca, modelo, anio.group())
        if results:
            lineas = "\n".join(f"- {format_part(p)}" for p in results)
            return (
                f"Modo sin IA (sin API key o fallo la llamada). "
                f"Busqueda directa en el inventario para {marca} {modelo} {anio.group()}:\n{lineas}"
            )
        return "Modo sin IA. " + diagnose_missing(inventory, marca, modelo, anio.group())

    return (
        "No puedo usar el LLM en este momento (falta API key o fallo la llamada). "
        "Modo sin IA: escribe marca, modelo y anio del vehiculo "
        "(ej: \"Suzuki Swift 2015\") o el codigo de un repuesto (ej: ALT-01) "
        "y busco en el inventario igual."
    )


def _run(
    agent_input: str, session_id: str = "default", max_retry_wait_s: float | None = None
) -> dict:
    """Ejecuta una interaccion completa del agente y devuelve el resultado."""
    inventory = get_inventory()
    agent = build_agent()
    guardrails: list[str] = []
    steps: list[dict] = []
    tokens = None
    used_llm = False
    limite_diario = False

    if agent is None or circuit_abierto():
        answer = (
            ("El servicio de IA esta en pausa breve por saturacion; reintente en unos segundos. ")
            if circuit_abierto() else ""
        ) + _fallback(agent_input)
        rate_limited = circuit_abierto()
        reintentos = 0
    else:
        reintentos = 0
        rate_limited = False
        try:
            result, reintentos, _ = _invoke_with_retry(
                agent,
                {"messages": _messages_for(agent_input, session_id)},
                max_wait_s=max_retry_wait_s,
            )
            messages = result.get("messages", [])
            steps = steps_from_messages(messages)
            tokens = _sum_tokens(messages)
            used_llm = True
            final = next(
                (m for m in reversed(messages) if m.__class__.__name__ == "AIMessage"),
                None,
            )
            content = getattr(final, "content", "") if final else ""
            if isinstance(content, list):
                content = "".join(
                    b.get("text", "") if isinstance(b, dict) else str(b) for b in content
                )
            answer = content or "(el modelo no devolvio texto)"
        except Exception as exc:
            print(f"(aviso) Fallo el agente: {exc.__class__.__name__}: {exc}")
            if is_daily_limit_error(exc):
                rate_limited = True
                limite_diario = True
                answer = _daily_limit_message(exc) + _fallback(agent_input)
            elif is_rate_limit_error(exc):
                rate_limited = True
                reintentos = RATE_LIMIT_RETRIES
                answer = _rate_limit_message() + _fallback(agent_input)
            else:
                answer = f"No pude completar la consulta con IA ({exc.__class__.__name__}). " + _fallback(
                    agent_input
                )

    # Guardrails: se aplican siempre, haya IA o no.
    answer, violations = apply_guardrails(answer, inventory)
    guardrails.extend(violations)

    # Memoria de corto plazo: solo si hubo una respuesta util.
    session = get_session(session_id)
    session.add("user", agent_input)
    session.add("assistant", answer)

    log_trace(
        session_id=session_id,
        entrada=agent_input,
        salida=answer,
        steps=steps,
        tokens=tokens,
        guardrails=guardrails,
        used_llm=used_llm,
        extra={
            "modelo": (get_provider_config() or {}).get("model"),
            "reintentos": reintentos,
            "rate_limited": rate_limited,
            "limite_diario": limite_diario,
        },
    )

    return {
        "respuesta": answer,
        "plan": steps,
        "tokens": tokens,
        "guardrails": guardrails,
        "used_llm": used_llm,
        "modelo": (get_provider_config() or {}).get("model"),
        "session_id": session_id,
        "reintentos": reintentos,
        "rate_limited": rate_limited,
        "limite_diario": limite_diario,
    }


def run(
    agent_input: str,
    session_id: str = "default",
    max_retry_wait_s: float | None = None,
    destinatario: str = "",
    usuario_id=None,
) -> dict:
    """Igual que ``_run``, con el contexto del usuario logueado por petición.

    Las variables de contexto se limpian siempre, incluso si falla la llamada,
    para que dos chats concurrentes no compartan destinatario ni memoria.
    """
    token_correo = usar_correo_sesion(destinatario)
    token_usuario = usar_usuario(usuario_id)
    token_sesion = usar_id_sesion(session_id)
    try:
        return _run(agent_input, session_id, max_retry_wait_s)
    finally:
        liberar_correo_sesion(token_correo)
        liberar_usuario(token_usuario)
        liberar_id_sesion(token_sesion)


def fallback_result(
    user_input: str, session_id: str = "default", retry_after: int | None = None
) -> dict:
    """Respuesta útil sin IA cuando el servicio está saturado o en pausa.

    Mantiene el mismo contrato que ``run`` para que la web pueda responder 200
    en vez de 503 sin romper la interfaz, los guardrails ni la trazabilidad.
    """
    inventory = get_inventory()
    answer, violations = apply_guardrails(_fallback(user_input), inventory)
    session = get_session(session_id)
    session.add("user", user_input)
    session.add("assistant", answer)
    log_trace(
        session_id=session_id,
        entrada=user_input,
        salida=answer,
        steps=[],
        tokens=None,
        guardrails=violations,
        used_llm=False,
        extra={
            "modelo": (get_provider_config() or {}).get("model"),
            "reintentos": 0,
            "rate_limited": True,
            "limite_diario": False,
            "saturado": True,
            "retry_after": retry_after,
        },
    )
    return {
        "respuesta": answer,
        "plan": [],
        "tokens": None,
        "guardrails": violations,
        "used_llm": False,
        "modelo": (get_provider_config() or {}).get("model"),
        "session_id": session_id,
        "reintentos": 0,
        "rate_limited": True,
        "limite_diario": False,
        "modo_sin_ia": True,
        "saturado": True,
        "retry_after": retry_after,
    }


def health(detailed: bool = True) -> dict:
    """Estado del LLM y de los datos.

    ``detailed=False`` es el modo publico del servidor web: no revela la ruta
    del indice, el modelo de embeddings ni la lista de herramientas.
    """
    cfg = get_provider_config()
    inventory = get_inventory()
    email_cfg = get_email_config()
    info = {
        "llm_disponible": cfg is not None,
        "proveedor": cfg["provider"] if cfg else None,
        "modelo": cfg["model"] if cfg else None,
        "repuestos": len(inventory),
        "correo_modo": email_cfg["modo"],
        "correo_configurado": email_cfg["modo"] == "smtp",
    }
    if detailed:
        info["memoria_largo_plazo"] = len(LongTermMemory.all())
        info["herramientas"] = [t.name for t in ALL_TOOLS]
    return info
