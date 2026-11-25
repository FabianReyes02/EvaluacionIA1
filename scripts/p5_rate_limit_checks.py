#!/usr/bin/env python3
"""P5: verificación de resiliencia ante 429/TPD sin gastar tokens del LLM.

Usa excepciones falsas y el circuit breaker del agente. Escribe
``tests/resultados/security/p5_rate_limit_checks.{json,md}``.
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
import sys

sys.path.insert(0, str(ROOT))

from agent import agent as agente  # noqa: E402
from agent import llm_client as llm  # noqa: E402


class RateLimitError(Exception):
    status_code = 429


class OpenAIRateLimitError(Exception):
    pass


class ErrorGenerico(Exception):
    pass


def ejecutar() -> dict:
    casos = []

    def add(cid: str, descripcion: str, ok: bool, detalle: str):
        casos.append(
            {"id": cid, "descripcion": descripcion, "ok": bool(ok), "detalle": detalle}
        )

    # 1) Detección de límite por minuto (reintentable).
    for cid, exc, esperado in [
        ("P5.1a", RateLimitError("429 too many requests"), True),
        ("P5.1b", OpenAIRateLimitError("rate_limit_exceeded"), True),
        ("P5.1c", ErrorGenerico("tpm limit reached"), True),
        ("P5.1d", ErrorGenerico("error de red"), False),
    ]:
        obtenido = llm.is_rate_limit_error(exc)
        add(cid, f"is_rate_limit_error({exc.__class__.__name__})", obtenido == esperado,
            f"esperado={esperado}, obtenido={obtenido}")

    # 2) Límite diario (NO reintentable).
    diario = ErrorGenerico("Rate limit reached on tokens per day (TPD): Limit 200000")
    por_minuto = ErrorGenerico("Rate limit reached, try again in 20s")
    add("P5.2a", "detecta TPD", llm.is_daily_limit_error(diario) is True, str(diario))
    add("P5.2b", "no confunde TPM con TPD", llm.is_daily_limit_error(por_minuto) is False,
        str(por_minuto))

    # 3) Hint de reinicio.
    hint = llm.daily_limit_reset_hint(ErrorGenerico("Please try again in 12m40.32s"))
    add("P5.3", "parsea tiempo de reinicio", hint == "12m", f"obtenido={hint!r}")
    hint_hora = llm.daily_limit_reset_hint(ErrorGenerico("try again in 1h5m"))
    add("P5.3b", "parsea horas", hint_hora == "1h 5m", f"obtenido={hint_hora!r}")

    # 4) Backoff solo ante 429.
    esperas = [round(llm.retry_delay_s(i), 1) for i in range(3)]
    base = llm.RATE_LIMIT_BASE_S
    add("P5.4", "backoff creciente", esperas == [base, 2 * base, 3 * base],
        f"esperas={esperas}, base={base}")

    # 5) Circuit breaker con mocks.
    threshold, cooldown = agente.CIRCUIT_THRESHOLD, agente.CIRCUIT_COOLDOWN_S
    try:
        agente.CIRCUIT_THRESHOLD = 2
        agente.CIRCUIT_COOLDOWN_S = 5
        agente._CIRCUIT["fallos"] = 0
        agente._CIRCUIT["abierto_hasta"] = 0.0
        agente.registrar_resultado(True)
        agente.registrar_resultado(True)
        abierto = agente.circuit_abierto()
        add("P5.5a", "se abre tras 2 429", abierto is True,
            f"fallos={agente._CIRCUIT['fallos']}")
        agente.registrar_resultado(False)
        add("P5.5b", "un OK reinicia el contador sin acortar el enfriamiento", (
            agente._CIRCUIT["fallos"] == 0 and agente.circuit_abierto() is True
        ), f"fallos={agente._CIRCUIT['fallos']}, sigue abierto hasta el cooldown")
        agente._CIRCUIT["abierto_hasta"] = time.time() - 1
        add("P5.5c", "se cierra solo tras el cooldown", agente.circuit_abierto() is False,
            "cooldown vencido")
        agente._CIRCUIT["fallos"] = 2
        agente._CIRCUIT["abierto_hasta"] = time.time() + 5
        agente.registrar_resultado(True, limite_diario=True)
        add("P5.5d", "TPD no dispara circuit breaker", agente.circuit_abierto() is False,
            "limite_diario=True reinicia el contador")
    finally:
        agente.CIRCUIT_THRESHOLD = threshold
        agente.CIRCUIT_COOLDOWN_S = cooldown
        agente._CIRCUIT["fallos"] = 0
        agente._CIRCUIT["abierto_hasta"] = 0.0

    # 6) Degradación elegante (misma respuesta que la web usa en vez de 503).
    salida = agente.fallback_result("Suzuki Swift 2015", session_id="p5", retry_after=7)
    add("P5.6", "saturación devuelve 200 con CSV", (
        salida["saturado"] is True and salida["modo_sin_ia"] is True
        and "ALT-01" in salida["respuesta"]
    ), f"retry_after={salida['retry_after']}")

    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "casos": casos,
        "resumen": {
            "total": len(casos),
            "ok": sum(1 for c in casos if c["ok"]),
            "fallos": [c["id"] for c in casos if not c["ok"]],
        },
    }


def main() -> int:
    datos = ejecutar()
    out_dir = ROOT / "tests" / "resultados" / "security"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "p5_rate_limit_checks.json").write_text(
        json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lineas = [
        "# P5 — Límites de tasa y circuit breaker (generado)",
        f"Fecha: {datos['timestamp']}",
        f"Resultado: {datos['resumen']['ok']}/{datos['resumen']['total']} correctos",
        "",
        "| Caso | Descripción | Resultado | Detalle |",
        "|---|---|---|---|",
    ]
    for c in datos["casos"]:
        lineas.append(
            f"| {c['id']} | {c['descripcion']} | {'OK' if c['ok'] else 'FALLO'} | {c['detalle']} |"
        )
    (out_dir / "p5_rate_limit_checks.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print(f"P5: {datos['resumen']['ok']}/{datos['resumen']['total']} correctos")
    print("Escrito:", out_dir / "p5_rate_limit_checks.md")
    return 0 if not datos["resumen"]["fallos"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
