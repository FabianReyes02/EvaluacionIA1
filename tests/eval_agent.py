"""Corre la suite de evaluacion del agente y genera evidencia de pruebas.

Uso (desde la raiz del proyecto):
    python tests/eval_agent.py                 # todos los casos
    python tests/eval_agent.py --solo C01,C07   # un subconjunto
    python tests/eval_agent.py --sin-reportar   # solo imprime

Salidas:
    tests/resultados/eval_reporte.json   detalle completo (insumo del informe)
    tests/resultados/eval_reporte.md     tabla resumen + justificaciones

Codigo de salida 0 si se cumple la meta (>= meta_aciertos%), 1 en caso contrario.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

# Memoria AISLADA para la evaluacion: no toca la memoria real del usuario y
# arranca vacia, asi los casos C13/C14 (escribir y leer entre sesiones) son
# deterministas aunque se haya usado el agente antes.
EVAL_MEMORY_FILE = ROOT_DIR / "data" / "memory" / "memoria_eval.jsonl"
os.environ["MEMORIA_FILE"] = str(EVAL_MEMORY_FILE)
os.environ["MEMORIA_COLLECTION"] = "memoria_eval"

from agent.agent import run  # noqa: E402
from agent.guardrails import extract_codes  # noqa: E402
from agent.memory import LongTermMemory, reset_session  # noqa: E402
from tools.inventory_lookup import ROOT, find_by_code, load_inventory  # noqa: E402

DATASET = Path(__file__).with_name("eval_dataset.json")
RESULTADOS = Path(__file__).parent / "resultados"
EXPORTS = ROOT / "data" / "exports"


def limpiar_memoria_eval() -> None:
    """Borra la memoria de largo plazo usada por la suite antes de empezar."""
    if EVAL_MEMORY_FILE.exists():
        EVAL_MEMORY_FILE.unlink()
    try:
        from agent.rag import get_client

        get_client().delete_collection("memoria_eval")
    except Exception:
        pass  # si la coleccion no existe, no hay nada que borrar


def contains_any(text: str, opciones: list[str]) -> bool:
    return any(o in text for o in opciones)


def evaluar(caso: dict, respuesta: str, resultado: dict, ctx: dict) -> tuple[bool, list[str]]:
    """Devuelve (aprobado, detalles). Cada criterio no cumplido queda en detalles."""
    esp = caso.get("esperado", {})
    detalles: list[str] = []
    inventario = ctx["inventory"]

    if esp.get("usa_llm") is True and not resultado["used_llm"]:
        detalles.append("no uso el LLM (esperaba respuesta con IA)")

    tools_usadas = [s["tool"] for s in resultado["plan"] if s.get("tipo") == "tool_call"]
    for tool in esp.get("debe_usar_tool", []):
        if tool not in tools_usadas:
            detalles.append(f"no uso la herramienta '{tool}' (uso: {tools_usadas or 'ninguna'})")
    for tool in esp.get("no_usar_tool", []):
        if tool in tools_usadas:
            detalles.append(f"usó la herramienta prohibida '{tool}'")

    for frag in esp.get("debe_contener", []):
        if frag not in respuesta:
            detalles.append(f"la respuesta no contiene '{frag}'")
    if esp.get("debe_contener_any") and not contains_any(respuesta, esp["debe_contener_any"]):
        detalles.append(f"no contiene ninguno de {esp['debe_contener_any']}")
    for frag in esp.get("no_debe_contener", []):
        if frag in respuesta:
            detalles.append(f"la respuesta contiene '{frag}' (no permitido)")

    # Guardrail esperado en esta interaccion.
    for esperado in esp.get("guardrails", []):
        if not any(g.startswith(esperado) for g in resultado["guardrails"]):
            detalles.append(f"no se activo el guardrail '{esperado}' (activo: {resultado['guardrails']})")

    # Regla global: ningun codigo mencionado puede ser inventado.
    if esp.get("no_codigos_inventados", True):
        marcados = {
            g.split(":", 1)[1]
            for g in resultado["guardrails"]
            if g.startswith("codigo_inexistente:")
        }
        inventados = [
            c
            for c in extract_codes(respuesta)
            if find_by_code(inventario, c) is None and c not in marcados
        ]
        if inventados:
            detalles.append(f"codigos inventados sin marcar: {inventados}")

    if esp.get("genera_archivo") and ctx["exports_after"] <= ctx["exports_before"]:
        detalles.append("no se creo ningun archivo en data/exports/")
    if esp.get("memoria_crece") and ctx["memoria_after"] <= ctx["memoria_before"]:
        detalles.append("la memoria de largo plazo no crecio")

    return (not detalles), detalles


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluacion del agente")
    parser.add_argument("--solo", default="", help="ids separados por coma (ej: C01,C07)")
    parser.add_argument("--sin-reportar", action="store_true", help="no escribe archivos")
    args = parser.parse_args()

    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    casos = dataset["casos"]
    if args.solo:
        ids = {i.strip().upper() for i in args.solo.split(",") if i.strip()}
        casos = [c for c in casos if c["id"] in ids]
        if not casos:
            print(f"Sin casos para {args.solo}")
            return 1

    inventory = load_inventory()
    total_tokens = 0
    resultados = []

    limpiar_memoria_eval()
    print(f"=== Evaluacion del agente ({len(casos)} casos) ===")
    print(f"Memoria de eval aislada: {EVAL_MEMORY_FILE}\n")
    for caso in casos:
        session = caso.get("session", f"eval-{caso['id']}")
        reset_session(session)  # aislamiento de la memoria de corto plazo
        memoria_before = len(LongTermMemory.all())
        exports_before = len(list(EXPORTS.glob("*.json"))) if EXPORTS.exists() else 0

        t0 = time.time()
        respuesta, resultado = "", {}
        for mensaje in caso["entradas"]:
            resultado = run(mensaje, session_id=session)
            respuesta = resultado["respuesta"]
        duracion = time.time() - t0
        if resultado.get("tokens"):
            total_tokens += resultado["tokens"]["total"]

        memoria_after = len(LongTermMemory.all())
        exports_after = len(list(EXPORTS.glob("*.json"))) if EXPORTS.exists() else 0
        ctx = {
            "inventory": inventory,
            "memoria_before": memoria_before,
            "memoria_after": memoria_after,
            "exports_before": exports_before,
            "exports_after": exports_after,
        }
        ok, detalles = evaluar(caso, respuesta, resultado, ctx)
        tools = [s["tool"] for s in resultado["plan"] if s.get("tipo") == "tool_call"]

        resultados.append(
            {
                "id": caso["id"],
                "tipo": caso["tipo"],
                "descripcion": caso["descripcion"],
                "entradas": caso["entradas"],
                "session": session,
                "aprobado": ok,
                "detalles": detalles,
                "justificacion": caso["justificacion"],
                "herramientas": tools,
                "guardrails": resultado["guardrails"],
                "used_llm": resultado["used_llm"],
                "tokens": resultado.get("tokens"),
                "duracion_s": round(duracion, 1),
                "respuesta": respuesta,
            }
        )
        marca = "OK  " if ok else "FAIL"
        print(f"[{marca}] {caso['id']} ({caso['tipo']}) {caso['descripcion']}")
        if not ok:
            for d in detalles:
                print(f"        - {d}")

    aprobados = sum(1 for r in resultados if r["aprobado"])
    pct = 100.0 * aprobados / len(resultados)
    meta = dataset["meta"]["meta_aciertos"]
    print(f"\nResultado: {aprobados}/{len(resultados)} ({pct:.1f}%) | meta: {meta}%")
    print(f"Tokens gastados: {total_tokens}")

    if not args.sin_reportar:
        RESULTADOS.mkdir(parents=True, exist_ok=True)
        reporte = {
            "fecha": datetime.now().isoformat(timespec="seconds"),
            "meta": meta,
            "aprobados": aprobados,
            "total": len(resultados),
            "porcentaje": round(pct, 1),
            "tokens": total_tokens,
            "resultados": resultados,
        }
        (RESULTADOS / "eval_reporte.json").write_text(
            json.dumps(reporte, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (RESULTADOS / "eval_reporte.md").write_text(
            _markdown(reporte), encoding="utf-8"
        )
        print(f"Reporte: {RESULTADOS / 'eval_reporte.md'}")

    return 0 if pct >= meta else 1


def _markdown(reporte: dict) -> str:
    lineas = [
        "# Evidencia de pruebas — Evaluacion del agente Repuestos Sur",
        "",
        f"**Fecha:** {reporte['fecha']}  ",
        f"**Resultado:** {reporte['aprobados']}/{reporte['total']} "
        f"({reporte['porcentaje']}%) — meta {reporte['meta']}%  ",
        f"**Tokens gastados:** {reporte['tokens']}",
        "",
        "| Caso | Tipo | Resultado | Herramientas | Guardrails | Tokens | Detalle |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in reporte["resultados"]:
        lineas.append(
            "| {id} | {tipo} | {ok} | {tools} | {g} | {t} | {d} |".format(
                id=r["id"],
                tipo=r["tipo"],
                ok="✅" if r["aprobado"] else "❌",
                tools=", ".join(r["herramientas"]) or "—",
                g=", ".join(r["guardrails"]) or "—",
                t=(r["tokens"] or {}).get("total", "—"),
                d="; ".join(r["detalles"]) or "cumple",
            )
        )
    lineas += ["", "## Detalle por caso", ""]
    for r in reporte["resultados"]:
        lineas += [
            f"### {r['id']} — {r['descripcion']} {'✅' if r['aprobado'] else '❌'}",
            f"- **Entrada:** {r['entradas']}",
            f"- **Por que se evalua:** {r['justificacion']}",
            f"- **Sesion:** `{r['session']}` | LLM: {r['used_llm']} | "
            f"duración {r['duracion_s']}s",
        ]
        if r["detalles"]:
            lineas.append(f"- **Fallas:** {'; '.join(r['detalles'])}")
        lineas += ["- **Respuesta:**", "", "```", r["respuesta"], "```", ""]
    return "\n".join(lineas)


if __name__ == "__main__":
    sys.exit(main())
