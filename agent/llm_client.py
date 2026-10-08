"""Cliente LLM intercambiable (Groq u OpenAI) sobre LangChain.

Un unico punto de configuracion para toda la aplicacion (CLI, agente y web):
lee `.env`, arma el `ChatOpenAI` del proveedor activo y expone una llamada
puntual (`ask_llm`) para los usos que no necesitan el loop del agente.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()

TEMPERATURE = 0.3

# Reintentos solo ante limite de tasa (HTTP 429 / OTPM de Groq, 1000 tok/min).
# Configurable por entorno para no alargar los evals mas de lo necesario.
RATE_LIMIT_RETRIES = int(os.getenv("AGENT_RETRY_ATTEMPTS", "3"))
RATE_LIMIT_BASE_S = float(os.getenv("AGENT_RETRY_BASE_S", "20"))

PROVIDERS: dict[str, dict] = {
    "openai": {
        "base_url": None,
        "key_env": "OPENAI_API_KEY",
        "model_env": "OPENAI_MODEL",
        "default_model": "gpt-4o-mini",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "key_env": "GROQ_API_KEY",
        "model_env": "GROQ_MODEL",
        # Verificado con scripts/_tmp_toolforce.py: soporta tool-calling.
        "default_model": "qwen/qwen3.8-27b",
    },
}


def get_provider_config() -> dict | None:
    """Configuracion del proveedor activo, o None si falta la API key.

    Devuelve provider, base_url, api_key y model; el caller no tiene que
    volver a leer ``.env``.
    """
    provider = os.getenv("LLM_PROVIDER", "groq").strip().lower()
    if provider not in PROVIDERS:
        provider = "openai"
    cfg = PROVIDERS[provider]
    api_key = (os.getenv(cfg["key_env"]) or "").strip()
    if not api_key:
        return None
    model = (os.getenv(cfg["model_env"]) or "").strip() or cfg["default_model"]
    return {
        "provider": provider,
        "base_url": cfg["base_url"],
        "api_key": api_key,
        "model": model,
        "key_env": cfg["key_env"],
    }


def get_chat_model(temperature: float = TEMPERATURE, **kwargs) -> ChatOpenAI | None:
    """Devuelve el ChatOpenAI del proveedor activo, o None si no hay key."""
    cfg = get_provider_config()
    if cfg is None:
        return None
    params = {"model": cfg["model"], "temperature": temperature, "api_key": cfg["api_key"]}
    if cfg["base_url"]:
        params["base_url"] = cfg["base_url"]
    params.update(kwargs)
    return ChatOpenAI(**params)


def usage_from(message) -> dict | None:
    """Extrae el uso de tokens de un AIMessage (o None si no viene reportado)."""
    meta = getattr(message, "usage_metadata", None)
    if meta:
        return {
            "prompt": meta.get("input_tokens", 0),
            "completion": meta.get("output_tokens", 0),
            "total": meta.get("total_tokens", 0),
        }
    legacy = (getattr(message, "response_metadata", None) or {}).get("token_usage")
    if legacy:
        return {
            "prompt": legacy.get("prompt_tokens", 0),
            "completion": legacy.get("completion_tokens", 0),
            "total": legacy.get("total_tokens", 0),
        }
    return None


def ask_llm(prompt: str, model: ChatOpenAI | None = None) -> tuple[str | None, dict | None]:
    """Llamada puntual de una sola vuelta. Devuelve (respuesta, tokens) o (None, None).

    Reintenta solo ante limite de tasa (429); otros errores fallan rapido para
    no duplicar llamadas pagadas.
    """
    llm = model or get_chat_model()
    if llm is None:
        return None, None
    intentos = max(0, RATE_LIMIT_RETRIES)
    for intento in range(intentos + 1):
        try:
            message = llm.invoke(prompt)
        except Exception as exc:
            if is_rate_limit_error(exc) and intento < intentos:
                _sleep_retry(intento, exc)
                continue
            print(f"(aviso) La llamada al LLM fallo: {exc.__class__.__name__}")
            return None, None
        content = message.content
        if isinstance(content, list):  # el modelo puede devolver bloques estructurados
            content = "".join(
                block.get("text", "") if isinstance(block, dict) else str(block) for block in content
            )
        return content, usage_from(message)
    return None, None


def is_rate_limit_error(exc: BaseException) -> bool:
    """True si la excepcion es un limite de tasa (HTTP 429 / OTPM) reintentable."""
    nombres = {c.__name__ for c in type(exc).__mro__}
    if nombres & {
        "RateLimitError",
        "OpenAIRateLimitError",
        "ModelRateLimitError",
        "TooManyRequestsError",
    }:
        return True
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if status == 429:
        return True
    texto = f"{exc.__class__.__name__}: {exc}".lower()
    return ("429" in texto or "rate_limit" in texto or "rate limit" in texto
            or "too many requests" in texto or "otpm" in texto or "tpm" in texto)


def retry_delay_s(intento: int) -> float:
    """Espera creciente: base * (intento + 1) -> 20s, 40s, 60s por defecto."""
    return RATE_LIMIT_BASE_S * (intento + 1)


def _sleep_retry(intento: int, exc: BaseException) -> None:
    import time

    espera = retry_delay_s(intento)
    print(f"(aviso) Limite de tasa ({exc.__class__.__name__}): "
          f"reintento {intento + 1}/{RATE_LIMIT_RETRIES} en {espera:.0f}s...")
    time.sleep(espera)


def add_tokens(a: dict | None, b: dict | None) -> dict | None:
    """Suma dos consumos de tokens (ignora los que no vienen reportados)."""
    if a is None:
        return b
    if b is None:
        return a
    return {
        "prompt": a["prompt"] + b["prompt"],
        "completion": a["completion"] + b["completion"],
        "total": a["total"] + b["total"],
    }
