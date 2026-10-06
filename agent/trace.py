"""Trazabilidad del agente: log JSONL con las decisiones tomadas (Requisito C).

Cada invocacion deja una linea en ``logs/trace.jsonl`` con la entrada, el plan
que siguio el modelo (tool -> argumentos -> observacion), la salida final, los
tokens y los guardrails que saltaron. Es la evidencia que se usa en los tests.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from tools.inventory_lookup import ROOT

LOGS_DIR = ROOT / "logs"
TRACE_FILE = LOGS_DIR / "trace.jsonl"

MAX_OBSERVACION = 300  # para que el archivo no se dispare


def steps_from_messages(messages) -> list[dict]:
    """Extrae la secuencia plan->observacion de los mensajes del agente."""
    steps = []
    for msg in messages:
        for tc in getattr(msg, "tool_calls", None) or []:
            # ToolCall puede venir como dict ({"name", "args"}) o como objeto.
            if isinstance(tc, dict):
                fn = tc.get("function") or tc
                name = fn.get("name")
                args = fn.get("args") if isinstance(fn, dict) else None
            else:
                fn = getattr(tc, "function", tc)
                name = getattr(fn, "name", None)
                args = getattr(fn, "args", None)
            steps.append({"tipo": "tool_call", "tool": name, "argumentos": args})
        if msg.__class__.__name__ == "ToolMessage":
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            steps.append(
                {
                    "tipo": "observacion",
                    "tool": getattr(msg, "name", None),
                    "resultado": content[:MAX_OBSERVACION],
                }
            )
    return steps


def log_trace(
    session_id: str,
    entrada: str,
    salida: str,
    steps: list[dict] | None = None,
    tokens: dict | None = None,
    guardrails: list[str] | None = None,
    used_llm: bool = True,
    extra: dict | None = None,
) -> dict:
    """Escribe una linea de traza y devuelve el registro completo."""
    registro = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "session_id": session_id,
        "entrada": entrada,
        "plan": steps or [],
        "salida": salida,
        "tokens": tokens,
        "guardrails": guardrails or [],
        "used_llm": used_llm,
    }
    if extra:
        registro.update(extra)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(TRACE_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False) + "\n")
    return registro


def read_trace(limit: int | None = None) -> list[dict]:
    """Lee las trazas (las ultimas ``limit`` si se indica)."""
    if not TRACE_FILE.exists():
        return []
    with open(TRACE_FILE, encoding="utf-8") as f:
        registros = [json.loads(line) for line in f if line.strip()]
    return registros[-limit:] if limit else registros
