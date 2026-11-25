#!/usr/bin/env python3
"""P3: fuzz basico contra la API web (stdlib), con autenticacion.

Asume que `python web/server.py` corre en http://127.0.0.1:8000 (o --port).
Ejemplo:
    python scripts/fuzz_api_web.py --port 8765 --username admin --password '...'
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.request import HTTPCookieProcessor, Request, build_opener

ROOT = Path(__file__).resolve().parent.parent


class Client:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()))

    def req(self, method: str, path: str, body=None, headers=None):
        hdrs = {"Accept": "application/json"}
        if headers:
            hdrs.update(headers)
        data = body
        r = Request(self.base + path, data=data, method=method, headers=hdrs)
        try:
            with self.opener.open(r, timeout=30) as resp:
                return resp.getcode(), resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", errors="replace")
        except Exception as e:
            return -1, f"{e.__class__.__name__}: {e}"


def run(port: int, username: str, password: str) -> list[dict]:
    base = f"http://127.0.0.1:{port}"
    cases: list[dict] = []
    anon = Client(base)
    auth = Client(base)

    def add(cid, ok, detail):
        cases.append({"id": cid, "ok": bool(ok), "detail": detail})

    # Sin sesion: solo publico, todo lo demas 401/303.
    code, _ = anon.req("GET", "/api/health")
    add("P3.0a", code == 200 and "repuestos" in _, f"health publico -> {code}")
    code, _ = anon.req("GET", "/api/inventory")
    add("P3.0b", code == 401, f"inventario sin sesion -> {code}")
    code, _ = anon.req("GET", "/")
    add("P3.0c", code in (303, 200), f"raiz sin sesion -> {code}")

    if username and password:
        code, txt = auth.req(
            "POST", "/api/login",
            json.dumps({"username": username, "password": password}).encode(),
            {"Content-Type": "application/json"},
        )
        add("P3.0d", code == 200, f"login -> {code}")
        code, _ = auth.req("GET", "/api/inventory")
        add("P3.0e", code == 200, f"inventario con admin -> {code}")
        code, _ = auth.req("GET", "/api/me")
        add("P3.0f", code == 200, f"/api/me -> {code}")
    else:
        add("P3.0d", False, "sin credenciales de admin; se omiten pruebas autenticadas")

    code, _ = auth.req("POST", "/api/chat", None, {"Content-Type": "application/json"})
    add("P3.2a", code == 400, f"chat sin body -> {code}")
    payload = json.dumps({"message": ""}).encode()
    code, _ = auth.req("POST", "/api/chat", payload, {"Content-Type": "application/json"})
    add("P3.2b", code == 400, f"mensaje vacio -> {code}")
    payload = json.dumps({"message": 12345, "session": "x" * 200}).encode()
    code, _ = auth.req("POST", "/api/chat", payload, {"Content-Type": "application/json"})
    add("P3.2c", code in (200, 400, 500), f"tipos raros -> {code} (no colapso)")
    payload = json.dumps({"message": "A" * (70 * 1024)}).encode()
    code, txt = auth.req("POST", "/api/chat", payload, {"Content-Type": "application/json"})
    add("P3.3", code == 400 and ("grande" in txt.lower() or "demasiado" in txt.lower()),
        f"big body -> {code}")

    code, _ = auth.req("GET", "/static/..%2f..%2f.env")
    add("P3.4a", code == 404, f"traversal encoded -> {code}")
    code, _ = auth.req("GET", "/static/../../.env")
    add("P3.4b", code in (400, 403, 404), f"traversal dots -> {code}")

    def hit_health(_):
        return anon.req("GET", "/api/health")[0]

    with ThreadPoolExecutor(max_workers=10) as ex:
        codes = [f.result() for f in as_completed([ex.submit(hit_health, i) for i in range(40)])]
    ok_burst = all(c == 200 for c in codes)
    add("P3.5", ok_burst, f"40 GET health paralelos: todos 200? {ok_burst}")
    return cases


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--username", default="")
    ap.add_argument("--password", default="")
    args = ap.parse_args()
    try:
        cases = run(args.port, args.username, args.password)
    except OSError as e:
        print(f"No se pudo conectar a 127.0.0.1:{args.port}: {e}")
        return 2

    out_dir = ROOT / "tests" / "resultados" / "security"
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {"timestamp": datetime.now().isoformat(timespec="seconds"), "port": args.port, "cases": cases}
    (out_dir / "p3_fuzz_api.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    fails = [c for c in cases if not c["ok"]]
    for c in cases:
        print(("OK  " if c["ok"] else "FAIL"), c["id"], c["detail"])
    print("Reporte:", out_dir / "p3_fuzz_api.json")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
