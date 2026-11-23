#!/usr/bin/env python3
"""P2: payloads maliciosos tipicos contra validadores y logica interna (sin LLM)."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
import sys

sys.path.insert(0, str(ROOT))

from tools.email_sender import dominio_permitido, validar_email
from agent.guardrails import extract_codes, normalizar_guiones
from tools.inventory_lookup import diagnose_missing, search_parts


def run() -> dict:
    results = {"timestamp": datetime.now().isoformat(timespec="seconds"), "cases": []}

    # P2.1 email
    for addr in ["", "a", "@@@", "user@localhost", "user@dominio.com", "x" * 260 + "@b.com", "bad\x00@b.com", "a b@b.com"]:
        ok, motivo = validar_email(addr)
        results["cases"].append({"test": "validar_email", "input": repr(addr)[:120], "ok": ok, "motivo": motivo})

    # P2.2 dominio
    results["cases"].append(
        {"test": "dominio_permitido", "input": "hacker@evil.com allow=[clientesur.cl]", "ok": dominio_permitido("hacker@evil.com", ["clientesur.cl"]) is False}
    )
    results["cases"].append(
        {"test": "dominio_permitido", "input": "ok@clientesur.cl allow=[clientesur.cl]", "ok": dominio_permitido("ok@clientesur.cl", ["clientesur.cl"]) is True}
    )
    results["cases"].append({"test": "dominio_permitido", "input": "x@y.com allow=[]", "ok": dominio_permitido("x@y.com", []) is True})

    # P2.3 guardrails
    texto = "Revisar ALT‐01 y ALT\u201102 y ALT-99"
    ng = normalizar_guiones(texto)
    codes = extract_codes(ng)
    results["cases"].append(
        {
            "test": "guardrails_unicode_guiones",
            "input": repr(texto),
            "ok": set(codes) >= {"ALT-01", "ALT-02", "ALT-99"},
            "codes": codes,
        }
    )
    results["cases"].append({"test": "guardrails_largo", "input": "texto largo", "ok": isinstance(extract_codes("x" * 50000), list)})

    # P2.4 inventory_lookup con inputs raros (sin tocar disco real si falla; usamos CSV real del repo)
    try:
        from tools.inventory_lookup import load_inventory

        inv = load_inventory()
        rare = [
            ("'; DROP TABLE repuestos; --", "Swift", "2015", ""),
            ("Suzuki", "Swift\" OR 1=1 --", "2015", ""),
            ("Suzuki", "Swift", "99999", ""),
            ("Suzuki", "Swift", "dos mil quince", ""),
            ("", "", "", ""),
        ]
        for marca, modelo, anio, tipo in rare:
            try:
                res = search_parts(inv, marca, modelo, anio, tipo=tipo)
                diag = diagnose_missing(inv, marca, modelo, anio)
                results["cases"].append(
                    {
                        "test": "search_parts_raro",
                        "input": {"marca": marca, "modelo": modelo, "anio": anio, "tipo": tipo},
                        "ok": isinstance(res, list) and isinstance(diag, str),
                        "n_resultados": len(res),
                    }
                )
            except Exception as exc:
                results["cases"].append(
                    {
                        "test": "search_parts_raro",
                        "input": {"marca": marca, "modelo": modelo, "anio": anio, "tipo": tipo},
                        "ok": False,
                        "error": f"{exc.__class__.__name__}: {exc}",
                    }
                )
    except Exception as exc:
        results["cases"].append({"test": "inventory_load", "ok": False, "error": str(exc)})

    return results


def main() -> int:
    out_dir = ROOT / "tests" / "resultados" / "security"
    out_dir.mkdir(parents=True, exist_ok=True)
    data = run()
    (out_dir / "p2_malicious_payloads.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    fails = [c for c in data["cases"] if c.get("ok") is False]
    print(f"P2: {len(data['cases'])} casos, fallos reportados: {len(fails)}")
    print("Escrito:", out_dir / "p2_malicious_payloads.json")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
