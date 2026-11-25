"""Memoria del agente: corto y largo plazo (Requisito B - IE3/IE4).

Corto plazo  -> ``ShortTermMemory``: ultimos N turnos de la conversacion de cada
                sesion. Le da coherencia a la tarea prolongada sin inflar tokens.
Largo plazo  -> ``LongTermMemory``: hechos que el agente decide persistir
                (``data/memory/memoria.jsonl`` + coleccion Chroma ``memoria``).
                Se escriben con la tool ``recordar_dato`` y se recuperan con
                ``recuperar_memoria`` (busqueda semantica), no con un volcado
                completo de la historia.
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from tools.inventory_lookup import ROOT

load_dotenv()

MEMORY_DIR = ROOT / "data" / "memory"
# Configurable por entorno para que los tests puedan usar una memoria aislada
# sin tocar la del usuario (ver tests/eval_agent.py).
MEMORY_FILE = Path(os.getenv("MEMORIA_FILE") or MEMORY_DIR / "memoria.jsonl")
COL_MEMORY = os.getenv("MEMORIA_COLLECTION", "memoria")

SHORT_TERM_WINDOW = 10  # turnos que se conservan en contexto (ventana deslizante)
# Un servidor que corre semanas no puede acumular sesiones ni hechos sin límite.
SESSION_TTL_S = int(os.getenv("CHAT_SESSION_TTL_S") or 8 * 3600)
MAX_SESSIONS = max(10, int(os.getenv("MAX_CHAT_SESSIONS") or 200))
MAX_LONG_TERM_REGISTROS = max(50, int(os.getenv("MAX_MEMORIA_REGISTROS") or 500))
_LONG_TERM_LOCK = threading.RLock()  # JSONL + indice semantico


# --------------------------------------------------------------------------
# Corto plazo
# --------------------------------------------------------------------------
class ShortTermMemory:
    """Historial de una sesion, recortado a los ultimos ``SHORT_TERM_WINDOW`` turnos."""

    def __init__(self, session_id: str, window: int = SHORT_TERM_WINDOW):
        self.session_id = session_id
        self.window = window
        self._turns: list[dict] = []  # {"role": user|assistant|system, "content": str}
        self._lock = threading.RLock()  # dos turnos de la misma sesion pueden llegar juntos
        self.last_used = time.time()

    def add(self, role: str, content: str) -> None:
        if not content:
            return
        with self._lock:
            self.last_used = time.time()
            self._turns.append({"role": role, "content": content})
            if len(self._turns) > self.window * 2:  # cada turno son 2 mensajes
                self._turns = self._turns[-(self.window * 2):]

    @property
    def turns(self) -> list[dict]:
        with self._lock:
            return list(self._turns)

    def as_messages(self):
        """Convierte a mensajes de LangChain para inyectarlas en el agente."""
        mapping = {"user": HumanMessage, "assistant": AIMessage, "system": SystemMessage}
        with self._lock:
            self.last_used = time.time()
            snapshot = list(self._turns)
        return [mapping.get(t["role"], HumanMessage)(content=t["content"]) for t in snapshot]

    def summary(self) -> str:
        """Resumen en texto del historial, para el system prompt."""
        with self._lock:
            self.last_used = time.time()
            recientes = list(self._turns[-6:])
        if not recientes:
            return "(sin interacciones previas en esta sesion)"
        lines = []
        for t in recientes:
            quien = "Cliente" if t["role"] == "user" else "Asistente"
            lines.append(f"{quien}: {t['content']}")
        return "\n".join(lines)

    def clear(self) -> None:
        with self._lock:
            self._turns.clear()


_SESSIONS: dict[str, ShortTermMemory] = {}
_LOCK = threading.Lock()


def get_session(session_id: str = "default") -> ShortTermMemory:
    """Sesion de memoria corto plazo (singleton por id, con TTL y LRU)."""
    ahora = time.time()
    with _LOCK:
        # Expiran primero las sesiones inactivas.
        for sid, ses in list(_SESSIONS.items()):
            if ahora - ses.last_used > SESSION_TTL_S:
                _SESSIONS.pop(sid, None)
        if session_id not in _SESSIONS:
            if len(_SESSIONS) >= MAX_SESSIONS:
                mas_vieja = min(_SESSIONS, key=lambda k: _SESSIONS[k].last_used)
                _SESSIONS.pop(mas_vieja, None)
            _SESSIONS[session_id] = ShortTermMemory(session_id)
        sesion = _SESSIONS[session_id]
        sesion.last_used = ahora
        return sesion


def reset_session(session_id: str = "default") -> None:
    with _LOCK:
        _SESSIONS.pop(session_id, None)


# --------------------------------------------------------------------------
# Largo plazo
# --------------------------------------------------------------------------
class LongTermMemory:
    """Hechos persistidos en disco (JSONL) + indice semantico en ChromaDB."""

    @staticmethod
    def record(dato: str, categoria: str = "general", origen: str = "") -> dict:
        """Escribe un hecho. Devuelve el registro guardado."""
        dato = (dato or "").strip()
        if not dato:
            raise ValueError("dato vacio")
        registro = {
            "id": uuid.uuid4().hex[:12],
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "categoria": (categoria or "general").strip(),
            "dato": dato,
            "origen": origen,
        }
        with _LONG_TERM_LOCK:
            MEMORY_DIR.mkdir(parents=True, exist_ok=True)
            with open(MEMORY_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(registro, ensure_ascii=False) + "\n")

            # Indice semantico (si Chroma está disponible; el JSONL siempre queda).
            try:
                from agent.rag import add_documents

                add_documents(
                    COL_MEMORY,
                    ids=[registro["id"]],
                    documents=[dato],
                    metadatas=[{k: str(v) for k, v in registro.items() if k != "dato"}],
                )
            except Exception as exc:
                registro["aviso_chroma"] = f"{exc.__class__.__name__}"

            # Tope de registros: el JSONL no crece sin límite en un servidor
            # que corre durante semanas.
            try:
                lineas = MEMORY_FILE.read_text(encoding="utf-8").splitlines()
                if len(lineas) > MAX_LONG_TERM_REGISTROS:
                    MEMORY_FILE.write_text(
                        "\n".join(lineas[-MAX_LONG_TERM_REGISTROS:]) + "\n",
                        encoding="utf-8",
                    )
            except Exception:
                pass
        return registro

    @staticmethod
    def search(consulta: str, k: int = 3) -> list[dict]:
        """Recuperacion semantica de hechos guardados."""
        try:
            from agent.rag import search as chroma_search

            hits = chroma_search(COL_MEMORY, consulta, k=k)
        except Exception:
            hits = []
        if hits:
            return [
                {"dato": h["documento"], "metadatos": h["metadatos"], "distancia": h["distancia"]}
                for h in hits
            ]
        # Fallback: ultimos registros del JSONL (si Chroma aun no esta indexado).
        registros = LongTermMemory.all()[-k:][::-1]
        return [{"dato": r["dato"], "metadatos": r, "distancia": None} for r in registros]

    @staticmethod
    def all() -> list[dict]:
        with _LONG_TERM_LOCK:
            if not MEMORY_FILE.exists():
                return []
            out = []
            with open(MEMORY_FILE, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        out.append(json.loads(line))
            return out

    @staticmethod
    def recent_context(limit: int = 5) -> str:
        """Hechos recientes listos para inyectar en el prompt del sistema.

        Limitaciones: recorta por orden de llegada, no por relevancia, y no
        distingue hechos contradictorios (si el cliente cambia de vehiculo,
        quedan ambos hasta que se sobrescriban manualmente).
        """
        registros = LongTermMemory.all()[-limit:]
        if not registros:
            return "(todavia no hay datos recordados del cliente)"
        return "\n".join(f"- [{r['categoria']}] {r['dato']} ({r['timestamp']})" for r in registros)
