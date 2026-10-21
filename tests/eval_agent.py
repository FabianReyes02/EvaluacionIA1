"""Corre la suite de evaluacion del agente y genera evidencia de pruebas.

Uso (desde la raiz del proyecto):
    python tests/eval_agent.py                 # todos los casos
    python tests/eval_agent.py --solo C01,C07   # un subconjunto
    python tests/eval_agent.py --sin-reportar   # solo imprime
    python tests/eval_agent.py --pausa 20       # espera S segundos entre casos
    python tests/eval_agent.py --parcial r.jsonl        # corrida por partes (reanuda)
    python tests/eval_agent.py --ensamblar r.jsonl      # arma el reporte final

La pausa entre casos existe para no agotar el cupo del plan gratuito de Groq
(8 000 tokens/min y 200 000 tokens/dia por modelo): con `--pausa 0` se corre lo
mas rapido posible (util solo con proveedor de pago o con cuota amplia).

Si el limite DIARIO de tokens no alcanza para la suite completa, la corrida por
partes (`--parcial`) guarda el resultado de cada caso, saltea los ya hechos al
reanudar y deja pendiente (no aprobado ni fallado) el caso que el proveedor
corta por cuota; `--ensamblar` genera el reporte final con lo juntado.

Salidas:
    tests/resultados/eval_reporte.json   detalle completo (insumo del informe)
    tests/resultados/eval_reporte.md     tabla resumen + justificaciones

Codigo de salida 0 si se cumple la meta (>= meta_aciertos%), 1 en caso contrario.
"""
from __future__ import annotations

import argparse
import json
import os
import re
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
from agent.llm_client import get_provider_config  # noqa: E402
from agent.memory import LongTermMemory, reset_session  # noqa: E402
from tools.inventory_lookup import ROOT, find_by_code, load_inventory  # noqa: E402

DATASET = Path(__file__).with_name("eval_dataset.json")
RESULTADOS = Path(__file__).parent / "resultados"
EXPORTS = ROOT / "data" / "exports"

# Modelo con el que se corre la suite (queda en la evidencia para que el
# reporte sea trazable: el limite diario de tokens de Groq es por modelo).
_cfg = get_provider_config() or {}
MODELO_EVAL = _cfg.get("model") or "(sin API key)"
PROVEEDOR_EVAL = _cfg.get("provider") or "-"

# Pausa por defecto entre casos (segundos): el plan gratuito de Groq limita a
# 8 000 tokens de salida/minuto por modelo y la suite completa lo agota;
# esperar entre casos evita que un 429 tire un caso a modo sin IA.
# Configurable con --pausa.
DEFAULT_PAUSA_S = 15.0


def limpiar_memoria_eval() -> None:
    """Borra la memoria de largo plazo usada por la suite antes de empezar."""
    if EVAL_MEMORY_FILE.exists():
        EVAL_MEMORY_FILE.unlink()
    try:
        from agent.rag import get_client

        get_client().delete_collection("memoria_eval")
    except Exception:
        pass  # si la coleccion no existe, no hay nada que borrar


def _norm(texto: str) -> str:
    """Normaliza texto para comparar: sin mayusculas, espacios ni signos.

    Asi '90A', '90 A' o '**90A**' (markdown) cuentan como la misma coincidencia:
    el criterio busca el dato, no el formato exacto de la redaccion del modelo.
    """
    return re.sub(r"[^0-9a-z\u00C0-\u024F]+", "", (texto or "").lower())


def contains_any(text: str, opciones: list[str]) -> bool:
    if any(o in text for o in opciones):
        return True
    norm = _norm(text)
    return any(_norm(o) in norm for o in opciones)


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
        if frag not in respuesta and _norm(frag) not in _norm(respuesta):
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


def _cargar_parcial(path: Path) -> dict[str, dict]:
    """Lee los resultados ya guardados de una corrida por partes."""
    guardados: dict[str, dict] = {}
    if not path.exists():
        return guardados
    for linea in path.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea:
            continue
        try:
            dato = json.loads(linea)
        except json.JSONDecodeError:
            continue
        if dato.get("id"):
            guardados[dato["id"]] = dato
    return guardados


def _escribir_reporte(resultados: list[dict], meta: int, fecha: str) -> dict:
    """Escribe eval_reporte.json y eval_reporte.md con los resultados dados."""
    RESULTADOS.mkdir(parents=True, exist_ok=True)
    aprobados = sum(1 for r in resultados if r["aprobado"])
    pct = round(100.0 * aprobados / len(resultados), 1) if resultados else 0.0
    total_tokens = sum((r.get("tokens") or {}).get("total", 0) for r in resultados)
    reporte = {
        "fecha": fecha,
        "proveedor": resultados[0].get("proveedor", "-") if resultados else "-",
        "modelo": resultados[0].get("modelo", "-") if resultados else "-",
        "meta": meta,
        "aprobados": aprobados,
        "total": len(resultados),
        "porcentaje": pct,
        "tokens": total_tokens,
        "resultados": resultados,
    }
    (RESULTADOS / "eval_reporte.json").write_text(
        json.dumps(reporte, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (RESULTADOS / "eval_reporte.md").write_text(_markdown(reporte), encoding="utf-8")
    return reporte


def _ensamblar(path: Path, dataset: dict) -> int:
    """Genera el reporte final a partir del JSONL de una corrida por partes."""
    guardados = _cargar_parcial(path)
    if not guardados:
        print(f"Sin resultados en {path}")
        return 1
    orden = [c["id"] for c in dataset["casos"]]
    resultados = [guardados[i] for i in orden if i in guardados]
    faltan = [i for i in orden if i not in guardados]
    meta = dataset["meta"]["meta_aciertos"]
    reporte = _escribir_reporte(
        resultados,
        meta,
        guardados[resultados[0]["id"]].get("fecha", datetime.now().isoformat(timespec="seconds")),
    )
    print(f"Reporte ensamblado: {reporte['aprobados']}/{reporte['total']} ({reporte['porcentaje']}%)")
    print(f"Tokens gastados: {reporte['tokens']}")
    if faltan:
        print(f"Faltan casos: {', '.join(faltan)}")
    print(f"Reporte: {RESULTADOS / 'eval_reporte.md'}")
    completa = not faltan and reporte["porcentaje"] >= meta
    return 0 if completa else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluacion del agente")
    parser.add_argument("--solo", default="", help="ids separados por coma (ej: C01,C07)")
    parser.add_argument("--sin-reportar", action="store_true", help="no escribe archivos")
    parser.add_argument(
        "--parcial",
        default="",
        help=(
            "archivo JSONL donde se guarda el resultado de cada caso; si ya "
            "existe, la corrida se reanuda y salta los casos ya hechos "
            "(util cuando el cupo diario del proveedor no alcanza para la suite "
            "completa de una sola vez)"
        ),
    )
    parser.add_argument(
        "--ensamblar",
        default="",
        help="genera el reporte final desde un JSONL de corrida por partes y sale",
    )
    parser.add_argument(
        "--pausa",
        type=float,
        default=DEFAULT_PAUSA_S,
        help=(
            "segundos de espera entre casos para respetar el cupo del plan "
            f"gratuito de Groq (8000 TPM); 0 = sin pausa (default: {DEFAULT_PAUSA_S:.0f})"
        ),
    )
    args = parser.parse_args()

    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    casos = dataset["casos"]
    if args.solo:
        ids = {i.strip().upper() for i in args.solo.split(",") if i.strip()}
        casos = [c for c in casos if c["id"] in ids]
        if not casos:
            print(f"Sin casos para {args.solo}")
            return 1

    if args.ensamblar:
        return _ensamblar(Path(args.ensamblar), dataset)

    parcial_path = Path(args.parcial) if args.parcial else None
    ya_hechos = _cargar_parcial(parcial_path) if parcial_path else {}
    if ya_hechos:
        print(f"Reanudando: {len(ya_hechos)} caso(s) ya hechos en {parcial_path}")

    inventory = load_inventory()
    total_tokens = 0
    resultados = []

    # La memoria de eval se limpia SOLO en una corrida desde cero: al reanudar
    # hay que conservarla, porque C13 escribe el dato que C14 lee en otra sesión.
    if not ya_hechos:
        limpiar_memoria_eval()
    print(f"=== Evaluacion del agente ({len(casos)} casos) ===")
    print(f"Proveedor: {PROVEEDOR_EVAL} | modelo: {MODELO_EVAL}")
    print(f"Memoria de eval aislada: {EVAL_MEMORY_FILE}")
    if args.pausa > 0:
        print(f"Pausa entre casos: {args.pausa:.0f}s (cupo Groq: 8000 TPM / 200000 TPD)")
    print()
    for indice, caso in enumerate(casos):
        if caso["id"] in ya_hechos:
            print(f"[SKIP] {caso['id']} ya estaba en {parcial_path}")
            continue
        if indice > 0 and args.pausa > 0:
            print(f"        ... esperando {args.pausa:.0f}s antes del siguiente caso")
            time.sleep(args.pausa)
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

        # Un caso que no llego al LLM por limite de tasa del proveedor no es un
        # fallo del agente: es una limitacion de infraestructura. No se cuenta
        # como aprobado ni como fallado, y la corrida se detiene para no gastar
        # cuota en casos que tampoco van a poder ejecutarse.
        bloqueado = resultado.get("rate_limited") and not resultado.get("used_llm")
        if bloqueado:
            motivo = "limite diario de tokens" if resultado.get("limite_diario") else "limite de tasa"
            print(f"[CUPO] {caso['id']} no se pudo evaluar ({motivo} del proveedor).")
            print("       Se deja pendiente: reintenta cuando se libere el cupo.")
            break

        resultados.append(
            {
                "id": caso["id"],
                "tipo": caso["tipo"],
                "descripcion": caso["descripcion"],
                "entradas": caso["entradas"],
                "session": session,
                "proveedor": PROVEEDOR_EVAL,
                "modelo": MODELO_EVAL,
                "fecha": datetime.now().isoformat(timespec="seconds"),
                "aprobado": ok,
                "detalles": detalles,
                "justificacion": caso["justificacion"],
                "herramientas": tools,
                "guardrails": resultado["guardrails"],
                "used_llm": resultado["used_llm"],
                "tokens": resultado.get("tokens"),
                "reintentos": resultado.get("reintentos", 0),
                "rate_limited": resultado.get("rate_limited", False),
                "limite_diario": resultado.get("limite_diario", False),
                "duracion_s": round(duracion, 1),
                "respuesta": respuesta,
            }
        )
        if parcial_path:
            with parcial_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(resultados[-1], ensure_ascii=False) + "\n")
        marca = "OK  " if ok else "FAIL"
        print(f"[{marca}] {caso['id']} ({caso['tipo']}) {caso['descripcion']}")
        if not ok:
            for d in detalles:
                print(f"        - {d}")

    aprobados = sum(1 for r in resultados if r["aprobado"])
    pct = 100.0 * aprobados / len(resultados) if resultados else 0.0
    meta = dataset["meta"]["meta_aciertos"]
    print(f"\nResultado: {aprobados}/{len(resultados)} ({pct:.1f}%) | meta: {meta}%")
    print(f"Tokens gastados: {total_tokens}")

    if parcial_path:
        # Corrida por partes: el reporte final se arma con --ensamblar.
        print(f"Resultados parciales en: {parcial_path}")
        print(f"Casos hechos en esta corrida: {len(resultados)}")
        return 0

    if not args.sin_reportar:
        reporte = _escribir_reporte(
            resultados, meta, datetime.now().isoformat(timespec="seconds")
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
        f"**Proveedor / modelo:** {reporte.get('proveedor', '-')} / "
        f"{reporte.get('modelo', '-')}  ",
        f"**Tokens gastados:** {reporte['tokens']}",
        "",
        "| Caso | Tipo | Resultado | Herramientas | Guardrails | Tokens | Reintentos | Detalle |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in reporte["resultados"]:
        lineas.append(
            "| {id} | {tipo} | {ok} | {tools} | {g} | {t} | {retry} | {d} |".format(
                id=r["id"],
                tipo=r["tipo"],
                ok="✅" if r["aprobado"] else "❌",
                tools=", ".join(r["herramientas"]) or "—",
                g=", ".join(r["guardrails"]) or "—",
                t=(r["tokens"] or {}).get("total", "—"),
                retry=r.get("reintentos", 0),
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
            f"duración {r['duracion_s']}s | reintentos 429: {r.get('reintentos', 0)}",
        ]
        if r["detalles"]:
            lineas.append(f"- **Fallas:** {'; '.join(r['detalles'])}")
        lineas += ["- **Respuesta:**", "", "```", r["respuesta"], "```", ""]
    return "\n".join(lineas)


if __name__ == "__main__":
    sys.exit(main())
