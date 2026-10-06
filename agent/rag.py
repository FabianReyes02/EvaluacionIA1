"""Ingesta y recuperacion RAG (Fase 1): manuales PDF + inventario CSV -> ChromaDB.

Dos colecciones persistentes en ``chroma_db/``:
  - ``manuales``   : fragmentos de los manuales tecnicos PDF (fuente externa).
  - ``inventario`` : filas del CSV (fuente interna), para recuperacion semantica.

Embeddings locales con ``paraphrase-multilingual-MiniLM-L12-v2`` (D2): sin costo
de API y pensados para contenido en espanol. La primera ejecucion descarga el
modelo (~470MB) una sola vez.
"""
from __future__ import annotations

import os
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter

from tools.inventory_lookup import INVENTORY_PATH, ROOT, load_inventory

MANUALS_DIR = ROOT / "data" / "external" / "manuales"
CHROMA_DIR = ROOT / "chroma_db"
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)

COL_MANUALS = "manuales"
COL_INVENTORY = "inventario"

# D4: 500/50 para que las especificaciones de un repuesto queden dentro del fragmento.
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50

_client = None
_embedding_fn = None


def get_client():
    """Cliente ChromaDB persistente (singleton: chromadb no permite dos para la misma ruta)."""
    global _client
    if _client is None:
        import chromadb

        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return _client


def get_embedding_fn():
    """Funcion de embeddings local (se carga una sola vez por proceso)."""
    global _embedding_fn
    if _embedding_fn is None:
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

        _embedding_fn = SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)
    return _embedding_fn


def get_collection(name: str):
    """Devuelve (creandola si hace falta) la coleccion pedida."""
    return get_client().get_or_create_collection(
        name=name, embedding_function=get_embedding_fn(), metadata={"hnsw:space": "cosine"}
    )


def _split(text: str) -> list[str]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP, separators=["\n\n", "\n", ". ", " ", ""]
    )
    return splitter.split_text(text)


def ingest_manuales(force: bool = False) -> dict:
    """Indexa los PDF de ``data/external/manuales``. Idempotente salvo ``force``."""
    collection = get_collection(COL_MANUALS)
    if not force and collection.count() > 0:
        return {"coleccion": COL_MANUALS, "documentos": collection.count(), "nuevo": False}

    if force:
        get_client().delete_collection(COL_MANUALS)
        collection = get_collection(COL_MANUALS)

    pdfs = sorted(MANUALS_DIR.glob("*.pdf"))
    if not pdfs:
        return {"coleccion": COL_MANUALS, "documentos": 0, "nuevo": False, "aviso": "sin PDF"}

    from pypdf import PdfReader

    ids, docs, metas = [], [], []
    for pdf in pdfs:
        reader = PdfReader(str(pdf))
        for page_no, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            for i, chunk in enumerate(_split(text)):
                if not chunk.strip():
                    continue
                base = f"{pdf.stem}-p{page_no}"
                ids.append(f"{base}-{i}")
                docs.append(chunk)
                metas.append(
                    {
                        "source": pdf.name,
                        "page": page_no,
                        "tipo_fuente": "manual",
                        "titulo": pdf.stem.replace("manual_", "").replace("_", " "),
                    }
                )
    if docs:
        collection.add(ids=ids, documents=docs, metadatas=metas)
    return {"coleccion": COL_MANUALS, "documentos": collection.count(), "nuevo": True}


def ingest_inventario(force: bool = False) -> dict:
    """Indexa las filas del CSV. Cada fila es un documento, sin partir (D4)."""
    collection = get_collection(COL_INVENTORY)
    if not force and collection.count() > 0:
        return {"coleccion": COL_INVENTORY, "documentos": collection.count(), "nuevo": False}

    if force:
        get_client().delete_collection(COL_INVENTORY)
        collection = get_collection(COL_INVENTORY)

    rows = load_inventory(INVENTORY_PATH)
    ids, docs, metas = [], [], []
    for row in rows:
        ids.append(row["codigo"])
        docs.append(
            f"{row['codigo']} - {row['descripcion']} (marca: {row['marca']}, "
            f"categoria: {row['categoria']}, precio: ${row['precio']}, stock: {row['stock']})\n"
            f"Vehiculos compatibles: {row['vehiculos_compatibles']}"
        )
        metas.append(
            {
                "codigo": row["codigo"],
                "marca": row["marca"],
                "categoria": row["categoria"],
                "precio": row["precio"],
                "stock": int(row["stock"]),
                "tipo_fuente": "inventario",
            }
        )
    if docs:
        collection.add(ids=ids, documents=docs, metadatas=metas)
    return {"coleccion": COL_INVENTORY, "documentos": collection.count(), "nuevo": True}


def ensure_index(force: bool = False) -> dict:
    """Garantiza que ambas colecciones existan y tengan datos."""
    return {
        "manuales": ingest_manuales(force=force),
        "inventario": ingest_inventario(force=force),
    }


def search(collection: str, query: str, k: int = 4) -> list[dict]:
    """Busqueda por similitud. Devuelve [{documento, metadatos, distancia}]."""
    query = (query or "").strip()
    if not query:
        return []
    col = get_collection(collection)
    if col.count() == 0:
        return []
    res = col.query(query_texts=[query], n_results=min(k, col.count()))
    out = []
    for doc, meta, dist in zip(
        res["documents"][0], res["metadatas"][0], res["distances"][0]
    ):
        out.append({"documento": doc, "metadatos": meta, "distancia": dist})
    return out


def stats() -> dict:
    """Conteo por coleccion + modelo de embeddings (para /api/health y verify_env)."""
    client = get_client()
    names = [c.name for c in client.list_collections()]
    return {
        "chroma_dir": str(CHROMA_DIR),
        "embedding_model": EMBEDDING_MODEL,
        "colecciones": {n: client.get_collection(n).count() for n in names},
    }
