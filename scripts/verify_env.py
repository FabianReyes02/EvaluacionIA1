"""Verifica el LLM activo (OpenAI/Groq), tool-calling, el agente, embeddings locales, ChromaDB y datos."""
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
)

LLM_CONFIG = {
    "openai": {
        "label": "OpenAI",
        "base_url": None,
        "key_env": "OPENAI_API_KEY",
        "model_env": "OPENAI_MODEL",
        "model_default": "gpt-4o-mini",
    },
    "groq": {
        "label": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "key_env": "GROQ_API_KEY",
        "model_env": "GROQ_MODEL",
        # Verificado: soporta tool-calling (groq/compound-mini ya no existe).
        "model_default": "qwen/qwen3.8-27b",
    },
}


def _check_data_files() -> bool:
    ok = True
    csv_path = os.path.join("data", "internal", "inventory.csv")
    if os.path.isfile(csv_path):
        print("✓ Inventario interno detectado (data/internal/inventory.csv)")
    else:
        print("✗ Falta data/internal/inventory.csv - ejecuta scripts/generate_sample_data.py")
        ok = False

    manuales_dir = os.path.join("data", "external", "manuales")
    if os.path.isdir(manuales_dir) and os.listdir(manuales_dir):
        pdfs = [f for f in os.listdir(manuales_dir) if f.lower().endswith(".pdf")]
        print(f"✓ Manuales externos detectados ({len(pdfs)} PDF en data/external/manuales/)")
    else:
        print("✗ Falta data/external/manuales/ - ejecuta scripts/generate_sample_data.py")
        ok = False
    return ok


def _check_llm(provider: str) -> bool:
    cfg = LLM_CONFIG[provider]
    key = os.getenv(cfg["key_env"], "")
    model = os.getenv(cfg["model_env"], cfg["model_default"])
    print(f"{cfg['key_env']} configurada: {bool(key)} (empieza con {key[:3] if key else '?'})")
    print(f"{cfg['model_env']}={model}")

    if not key:
        print(f"✗ Falta {cfg['key_env']} - copia .env.example a .env y edítala")
        return False

    try:
        from openai import OpenAI

        if cfg["base_url"]:
            cliente = OpenAI(api_key=key, base_url=cfg["base_url"])
        else:
            cliente = OpenAI(api_key=key)
        respuesta = cliente.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Responde solo: OK"}],
            max_tokens=50,
        )
        contenido = respuesta.choices[0].message.content.strip()
        print(f"✓ {cfg['label']} responde ({model}): {contenido!r}")
    except Exception as e:
        print(f"✗ {cfg['label']} error: {e}")
        return False
    return True


def _check_tool_calling(provider: str) -> bool:
    """El agente necesita un modelo que emita tool_calls: lo verifica en vivo."""
    cfg = LLM_CONFIG[provider]
    key = os.getenv(cfg["key_env"], "")
    if not key:
        return False
    model = os.getenv(cfg["model_env"], cfg["model_default"])
    tools = [
        {
            "type": "function",
            "function": {
                "name": "buscar_repuesto",
                "description": "Busca repuestos en el inventario",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "marca": {"type": "string"},
                        "modelo": {"type": "string"},
                        "anio": {"type": "string"},
                    },
                    "required": ["marca", "modelo", "anio"],
                },
            },
        }
    ]
    try:
        from openai import OpenAI

        if cfg["base_url"]:
            cliente = OpenAI(api_key=key, base_url=cfg["base_url"])
        else:
            cliente = OpenAI(api_key=key)
        r = cliente.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Busca repuestos para Suzuki Swift 2015"}],
            tools=tools,
            tool_choice="required",
            # max_tokens acotado: algunos modelos calculan salidas enormes con
            # tool_choice=required y el plan gratuito de Groq limita a 1000 OTPM.
            max_tokens=200,
        )
        calls = r.choices[0].message.tool_calls or []
        if not calls:
            print(f"✗ {model} NO emite tool_calls: el agente no puede funcionar")
            return False
        print(f"✓ {model} emite tool_calls: {calls[0].function.name}")
        return True
    except Exception as e:
        print(f"✗ Tool-calling no disponible en {model}: {e}")
        print("  Cambia GROQ_MODEL en .env (ej: qwen/qwen3.8-27b u openai/gpt-oss-20b)")
        return False


def main() -> int:
    provider = os.getenv("LLM_PROVIDER", "openai")
    if provider not in LLM_CONFIG:
        print(f"⚠ LLM_PROVIDER desconocido ({provider}), usando openai")
        provider = "openai"
    print(f"LLM_PROVIDER={provider}")
    print(f"EMBEDDING_MODEL={EMBEDDING_MODEL}")

    if not _check_data_files():
        return 1

    if not _check_llm(provider):
        return 1

    if not _check_tool_calling(provider):
        return 1

    try:
        print("[..] Construyendo el agente LangChain...")
        from agent.agent import build_agent

        if build_agent() is None:
            print("✗ No se pudo construir el agente (sin API key)")
            return 1
        from agent.tools import ALL_TOOLS

        print(f"✓ Agente OK con {len(ALL_TOOLS)} herramientas: "
              f"{', '.join(t.name for t in ALL_TOOLS)}")
    except Exception as e:
        print(f"✗ Agente error: {e}")
        return 1

    try:
        print("[..] Cargando embeddings locales (primera vez descarga ~470MB)...")
        from chromadb.utils.embedding_functions import (
            SentenceTransformerEmbeddingFunction,
        )

        ef = SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)
        dim = len(ef(["prueba"])[0])
        print(f"✓ Embeddings locales OK: dim={dim}")
    except Exception as e:
        print(f"✗ Embeddings error: {e}")
        return 1

    try:
        import chromadb

        ef_st = SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)
        cliente_chroma = chromadb.EphemeralClient()
        col = cliente_chroma.get_or_create_collection("verify", embedding_function=ef_st)
        col.add(ids=["1"], documents=["prueba de ingesta"])
        res = col.query(query_texts=["prueba"], n_results=1)
        print(f"✓ ChromaDB OK (recuperado: {res['documents'][0][0]!r})")
    except Exception as e:
        print(f"✗ ChromaDB error: {e}")
        return 1

    print("Listo: LLM, embeddings, ChromaDB y datos de ejemplo funcionan correctamente")
    return 0


if __name__ == "__main__":
    sys.exit(main())