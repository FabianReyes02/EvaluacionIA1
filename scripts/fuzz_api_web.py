#!/usr/bin/env python3
"""P3: fuzz basico contra la API web del servidor local (stdlib).

Levanta el servidor en un hilo no es trivial aqui; este script asume que
`python web/server.py` corre en http://127.0.0.1:8000 (o usar --port).

Ejemplo:
    # en otra terminal: python web/server.py 8765
    python scripts/fuzz_api_web.py --port 8765
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def req(method: str, url: str, body: bytes | None = None, headers: dict | None = None) -> tuple[int, str]:
    hdrs = {"Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    r = urllib.request.Request(url, data=body, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.getcode(), resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")
    except Exception as e:
        return -1, f"{e.__class__.__name__}: {e}"


def run(port: int) -> list[dict]:
    base = f"http://127.0.0.1:{port}"
    cases: list[dict] = []

    # P3.1
    code, _ = req("GET", f"{base}/")
    cases.append({"id": "P3.1a", "ok": code == 200, "detail": f"GET / -> {code}"})
    code, txt = req("GET", f"{base}/api/health")
    cases.append({"id": "P3.1b", "ok": code == 200 and "repuestos" in txt, "detail": f"health {code}"})
    code, txt = req("GET", f"{base}/api/inventory")
    cases.append({"id": "P3.1c", "ok": code == 200 and "parts" in txt, "detail": f"inventory {code}"})

    # P3.2 POST chat
    code, _ = req("POST", f"{base}/api/chat", body=None, headers={"Content-Type": "application/json"})
    cases.append({"id": "P3.2a", "ok": code == 400, "detail": f"chat sin body -> {code}"})

    payload = json.dumps({"message": ""}).encode()
    code, _ = req("POST", f"{base}/api/chat", body=payload, headers={"Content-Type": "application/json"})
    cases.append({"id": "P3.2b", "ok": code == 400, "detail": f"mensaje vacio -> {code}"})

    payload = json.dumps({"message": 12345, "session": "x" * 200}).encode()
    code, _ = req("POST", f"{base}/api/chat", body=payload, headers={"Content-Type": "application/json"})
    cases.append({"id": "P3.2c", "ok": code in (200, 400, 500), "detail": f"tipos raros -> {code} (no colapso)"})

    # P3.3 cuerpo grande >64KB
    big = json.dumps({"message": "A" * (70 * 1024)}).encode()
    code, txt = req("POST", f"{base}/api/chat", body=big, headers={"Content-Type": "application/json"})
    cases.append({"id": "P3.3", "ok": code == 400 and "grande" in txt.lower() or "demasiado" in txt.lower(), "detail": f"big body -> {code}"})

    # P3.4 path traversal
    code, _ = req("GET", f"{base}/static/..%2f..%2f.env")
    cases.append({"id": "P3.4a", "ok": code == 404, "detail": f"traversal encoded -> {code}"})
    code, _ = req("GET", f"{base}/static/../../.env")
    cases.append({"id": "P3.4b", "ok": code in (400, 403, 404), "detail": f"traversal dots -> {code}"})

    # P3.5 rafaga ligera sobre endpoints rapidos
    def hit_health(_):
        c, _ = req("GET", f"{base}/api/health")
        return c

    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = [ex.submit(hit_health, i) for i in range(40)]
        codes = [f.result() for f in as_completed(futs)]
    ok_burst = all(c == 200 for c in codes)
    cases.append({"id": "P3.5", "ok": ok_burst, "detail": f"40 GET health paralelos: todos 200? {ok_burst}"})

    return cases


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    try:
        cases = run(args.port)
    except OSError as e:
        print(f"No se pudo conectar a 127.0.0.1:{args.port}: {e}")
        print("Inicia primero: python web/server.py", args.port)
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
