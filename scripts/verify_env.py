"""Verifica OPENAI_API_KEY, embeddings locales, ChromaDB y datos antes de correr el agente."""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv

load_dotenv()

EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
)


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


def main() -> int:
    provider = os.getenv("LLM_PROVIDER", "openai")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    print(f"LLM_PROVIDER={provider}")
    print(f"OPENAI_MODEL={model}")
    print(f"EMBEDDING_MODEL={EMBEDDING_MODEL}")

    key = os.getenv("OPENAI_API_KEY", "")
    print(f"OPENAI_API_KEY configurada: {bool(key)} (empieza con {key[:3] if key else '?'})")

    if not _check_data_files():
        return 1

    if not key:
        print("✗ Falta OPENAI_API_KEY - copia .env.example a .env y edítala")
        return 1

    try:
        from openai import OpenAI

        cliente = OpenAI()
        respuesta = cliente.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Responde solo: OK"}],
            max_completion_tokens=50,
        )
        contenido = respuesta.choices[0].message.content.strip()
        print(f"✓ OpenAI responde ({model}): {contenido!r}")
    except Exception as e:
        print(f"✗ OpenAI error: {e}")
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

    print("Listo: OpenAI, embeddings, ChromaDB y datos de ejemplo funcionan correctamente")
    return 0


if __name__ == "__main__":
    sys.exit(main())