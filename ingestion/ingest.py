"""Ingesta RAG: indexa los manuales PDF y el inventario CSV en ChromaDB.

Uso:
    python ingestion/ingest.py            # ingesta idempotente (solo si falta)
    python ingestion/ingest.py --force    # reconstruye el indice desde cero
    python ingestion/ingest.py --stats    # muestra el estado del indice

Chunking 500/50 sobre los PDF; las filas del CSV se indexan completas (D4).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.rag import ensure_index, stats  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingesta RAG a ChromaDB")
    parser.add_argument("--force", action="store_true", help="reconstruye el indice")
    parser.add_argument("--stats", action="store_true", help="solo muestra el estado")
    args = parser.parse_args()

    if args.stats:
        print(json.dumps(stats(), ensure_ascii=False, indent=2))
        return 0

    print("Indexando manuales PDF + inventario CSV (primera vez descarga ~470MB)...")
    try:
        result = ensure_index(force=args.force)
    except Exception as exc:
        print(f"✗ Fallo la ingesta: {exc.__class__.__name__}: {exc}")
        return 1

    for nombre, info in result.items():
        nuevo = "indexado ahora" if info.get("nuevo") else "ya estaba indexado"
        print(f"  {nombre}: {info['documentos']} documento(s) -> {nuevo}")
    print(json.dumps(stats(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
