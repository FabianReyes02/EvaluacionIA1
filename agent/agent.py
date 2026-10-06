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

import re

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, SystemMessage

from agent.guardrails import apply as apply_guardrails
from agent.llm_client import get_chat_model, get_provider_config, usage_from
from agent.memory import LongTermMemory, get_session
from agent.prompts import SYSTEM_PROMPT, build_context_block
from agent.tools import ALL_TOOLS, get_inventory
from agent.trace import log_trace, steps_from_messages
from tools.inventory_lookup import (
    diagnose_missing,
    find_by_code,
    format_part,
    get_catalog_summary,
    search_parts,
)

_agent = None
_agent_model_id = None


def build_agent():
    """Compila el agente de LangChain (singleton por modelo)."""
    global _agent, _agent_model_id
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


def _messages_for(agent_input: str, session_id: str) -> list:
    """Bloque de contexto + historial de corto plazo + mensaje nuevo."""
    inventory = get_inventory()
    context = build_context_block(
        catalog=get_catalog_summary(inventory),
        memoria=LongTermMemory.recent_context(),
        historial=get_session(session_id).summary(),
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


def run(agent_input: str, session_id: str = "default") -> dict:
    """Ejecuta una interaccion completa del agente y devuelve el resultado."""
    inventory = get_inventory()
    agent = build_agent()
    guardrails: list[str] = []
    steps: list[dict] = []
    tokens = None
    used_llm = False

    if agent is None:
        answer = _fallback(agent_input)
    else:
        try:
            result = agent.invoke({"messages": _messages_for(agent_input, session_id)})
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
        extra={"modelo": (get_provider_config() or {}).get("model")},
    )

    return {
        "respuesta": answer,
        "plan": steps,
        "tokens": tokens,
        "guardrails": guardrails,
        "used_llm": used_llm,
        "modelo": (get_provider_config() or {}).get("model"),
        "session_id": session_id,
    }


def health() -> dict:
    """Estado del LLM y de los datos para la interfaz (/api/health)."""
    cfg = get_provider_config()
    inventory = get_inventory()
    return {
        "llm_disponible": cfg is not None,
        "proveedor": cfg["provider"] if cfg else None,
        "modelo": cfg["model"] if cfg else None,
        "repuestos": len(inventory),
        "memoria_largo_plazo": len(LongTermMemory.all()),
        "herramientas": [t.name for t in ALL_TOOLS],
    }
