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
    """Llamada puntual de una sola vuelta. Devuelve (respuesta, tokens) o (None, None)."""
    llm = model or get_chat_model()
    if llm is None:
        return None, None
    try:
        message = llm.invoke(prompt)
    except Exception as exc:
        print(f"(aviso) La llamada al LLM fallo: {exc.__class__.__name__}")
        return None, None
    content = message.content
    if isinstance(content, list):  # el modelo puede devolver bloques estructurados
        content = "".join(
            block.get("text", "") if isinstance(block, dict) else str(block) for block in content
        )
    return content, usage_from(message)


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
