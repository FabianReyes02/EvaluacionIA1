#!/usr/bin/env python3
"""P3 contra la URL pública desplegada (HTTPS con certificado autofirmado).

Uso:
    python scripts/fuzz_public_url.py --base https://34.201.171.124

Solo crea un usuario de prueba con correo ficticio; no envía correos ni hace
consultas al LLM. Escribe tests/resultados/security/p3_public_url.{json,md}.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import ssl
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.request import (
    HTTPCookieProcessor, HTTPSHandler, HTTPRedirectHandler, Request, build_opener,
)

ROOT = Path(__file__).resolve().parent.parent


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def run(base: str) -> dict:
    base = base.rstrip("/")
    handlers = []
    if base.startswith("https://"):
        handlers.append(HTTPSHandler(context=ssl._create_unverified_context()))
    sesion = build_opener(*handlers, HTTPCookieProcessor(CookieJar()))
    sin_redirect = build_opener(*handlers, NoRedirect(), HTTPCookieProcessor(CookieJar()))
    casos = []

    def add(cid: str, ok: bool, detalle: str):
        casos.append({"id": cid, "ok": bool(ok), "detalle": detalle})

    def req(opener, url, method="GET", body=None, headers=None):
        r = Request(url, data=body, headers=headers or {}, method=method)
        try:
            with opener.open(r, timeout=30) as resp:
                return resp.status, resp.headers, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()

    code, headers, _ = req(sesion, base + "/api/health")
    add("P3.1", code == 200, f"health -> {code}")
    add("P3.2", "Strict-Transport-Security" in headers, "HSTS presente en health")

    http_base = "http://" + base.split("://", 1)[1]
    code, headers, _ = req(sin_redirect, http_base + "/api/health")
    add("P3.3", code == 301 and headers.get("Location", "").startswith("https://"),
        f"HTTP -> {code} {headers.get('Location', '')}")

    for cid, path, esperado in [
        ("P3.4", "/", 303), ("P3.5", "/admin", 303), ("P3.6", "/api/inventory", 401)
    ]:
        code, _, _ = req(sin_redirect, base + path)
        add(cid, code == esperado, f"{path} anonimo -> {code}")

    code, headers, html = req(sesion, base + "/login")
    csp = headers.get("Content-Security-Policy", "")
    add("P3.7", code == 200 and "nonce-" in csp and "unsafe-inline" not in csp,
        "CSP con nonce y sin unsafe-inline")

    user = "fuzz_" + uuid.uuid4().hex[:8]
    payload = json.dumps(
        {"username": user, "password": "ClaveFuzz123!", "email": f"{user}@lab"}
    ).encode()
    code, _, _ = req(sesion, base + "/api/register", "POST", payload,
                     {"Content-Type": "application/json"})
    add("P3.8", code == 200, f"registro de prueba -> {code}")
    payload = json.dumps({"username": user, "password": "ClaveFuzz123!"}).encode()
    code, headers, _ = req(sesion, base + "/api/login", "POST", payload,
                           {"Content-Type": "application/json"})
    add("P3.9", code == 200 and "Secure" in (headers.get("Set-Cookie") or ""),
        f"login -> {code}, cookie Secure={'Secure' in (headers.get('Set-Cookie') or '')}")

    code, _, _ = req(sesion, base + "/api/chat", "POST", b"hola", {"Content-Type": "text/plain"})
    add("P3.10", code == 415, f"Content-Type incorrecto -> {code}")

    code, _, _ = req(
        sesion, base + "/api/chat", "POST",
        json.dumps({"message": "A" * (70 * 1024)}).encode(),
        {"Content-Type": "application/json"},
    )
    add("P3.11", code == 400, f"cuerpo grande -> {code}")

    for cid, path in [
        ("P3.12", "/static/..%2f..%2f.env"),
        ("P3.13", "/static/../../.env"),
    ]:
        code, _, _ = req(sesion, base + path)
        add(cid, code in (400, 403, 404),
            f"traversal -> {code} (Nginx puede rechazar con 400 antes de la app)")

    code, _, _ = req(
        sesion, base + "/api/login", "POST", b"{}",
        {"Content-Type": "application/json", "Origin": "http://evil.example"},
    )
    add("P3.14", code == 403, f"Origin cross-site -> {code}")

    def health(_):
        return req(sesion, base + "/api/health")[0]

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
        codes = list(ex.map(health, range(20)))
    add("P3.15", all(c == 200 for c in codes), f"20 GET paralelos: todos 200? {all(c == 200 for c in codes)}")

    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "base": base,
        "casos": casos,
        "resumen": {
            "total": len(casos),
            "ok": sum(1 for c in casos if c["ok"]),
            "fallos": [c["id"] for c in casos if not c["ok"]],
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://34.201.171.124")
    args = ap.parse_args()
    datos = run(args.base)
    out_dir = ROOT / "tests" / "resultados" / "security"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "p3_public_url.json").write_text(
        json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lineas = [
        "# P3 — Fuzz contra la URL pública (generado)",
        f"Fecha: {datos['timestamp']}",
        f"Base: {datos['base']}",
        f"Resultado: {datos['resumen']['ok']}/{datos['resumen']['total']} correctos",
        "",
        "| Caso | Resultado | Detalle |",
        "|---|---|---|",
    ]
    for c in datos["casos"]:
        lineas.append(f"| {c['id']} | {'OK' if c['ok'] else 'FALLO'} | {c['detalle']} |")
    (out_dir / "p3_public_url.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print(f"P3 publico: {datos['resumen']['ok']}/{datos['resumen']['total']} correctos")
    print("Escrito:", out_dir / "p3_public_url.md")
    return 0 if not datos["resumen"]["fallos"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
