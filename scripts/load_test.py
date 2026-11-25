#!/usr/bin/env python3
"""Prueba de carga concurrente contra el servidor web (stdlib).

Registra N usuarios, los loguea y dispara consultas al chat en paralelo.
Tambien verifica la matriz de roles: el cliente NO ve inventario ni /admin.

Ejemplo:
    python scripts/load_test.py --url http://54.87.5.227 \
        --users 10 --requests 1 --admin-user admin --admin-password '...'
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.request import HTTPCookieProcessor, Request, build_opener

ROOT = Path(__file__).resolve().parent.parent


class Client:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.jar = CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.jar))

    def req(self, method: str, path: str, body: dict | None = None, timeout: int = 180):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        r = Request(self.base + path, data=data, method=method, headers=headers)
        t0 = time.perf_counter()
        try:
            with self.opener.open(r, timeout=timeout) as resp:
                return resp.getcode(), resp.read().decode("utf-8", errors="replace"), time.perf_counter() - t0
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", errors="replace"), time.perf_counter() - t0
        except Exception as e:
            return -1, f"{e.__class__.__name__}: {e}", time.perf_counter() - t0


def p95(vals: list[float]) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    return round(s[min(len(s) - 1, int(len(s) * 0.95))], 3)


def run(args) -> dict:
    sufijo = uuid.uuid4().hex[:6]
    users: list[tuple[str, Client]] = []
    latencias: list[float] = []
    estados: Counter = Counter()
    errores: list[str] = []
    saturados = 0

    base_client = Client(args.url)
    code, txt, _ = base_client.req("GET", "/api/health", timeout=20)
    salud = {"code": code, "body": txt[:300]}
    if code != 200:
        return {"ok": False, "health": salud, "error": "el servidor no responde"}

    # 1) registro abierto + login de cada usuario
    for i in range(args.users):
        username = f"lab_{sufijo}_{i}"
        password = "CargaLaboratorio123!"
        c = Client(args.url)
        code, txt, _ = c.req(
            "POST", "/api/register",
            {"username": username, "password": password, "email": f"{username}@lab"},
            timeout=30,
        )
        if code not in (200, 400):  # 400 si el nombre ya existe en una corrida repetida
            errores.append(f"registro {username}: {code} {txt[:120]}")
            continue
        code, txt, _ = c.req("POST", "/api/login", {"username": username, "password": password}, timeout=30)
        if code != 200:
            errores.append(f"login {username}: {code} {txt[:120]}")
            continue
        users.append((username, c))

    if not users:
        return {"ok": False, "health": salud, "errores": errores}

    # 2) consultas al chat en paralelo (una por usuario por ronda)
    def chat(item):
        username, c, ronda = item
        mensaje = "Suzuki Swift 2015" if ronda == 0 else "ALT-01"
        code, txt, dt = c.req("POST", "/api/chat", {"message": mensaje, "session": f"load-{sufijo}"},
                              timeout=args.timeout)
        return username, ronda, code, txt, dt

    tareas = [(u, c, r) for u, c in users for r in range(args.requests)]
    with ThreadPoolExecutor(max_workers=min(args.users, 20)) as ex:
        for fut in as_completed([ex.submit(chat, t) for t in tareas]):
            username, ronda, code, txt, dt = fut.result()
            estados[str(code)] += 1
            latencias.append(dt)
            if code == 503:
                # Respuesta controlada de la cola/circuit breaker: no es un crash.
                saturados += 1
            elif code == 500 or code == -1:
                errores.append(f"chat {username} ronda {ronda}: {code} {txt[:160]}")

    # 3) matriz de permisos
    permisos: dict[str, object] = {}
    anon = Client(args.url)
    permisos["anon_inventory"] = anon.req("GET", "/api/inventory", timeout=20)[0]
    permisos["anon_root"] = anon.req("GET", "/", timeout=20)[0]
    cliente = users[0][1]
    permisos["cliente_inventory"] = cliente.req("GET", "/api/inventory", timeout=20)[0]
    permisos["cliente_admin"] = cliente.req("GET", "/admin", timeout=20)[0]
    permisos["cliente_chat"] = cliente.req("POST", "/api/chat", {"message": "hola"}, timeout=args.timeout)[0]
    permisos["health"] = anon.req("GET", "/api/health", timeout=20)[0]

    if args.admin_user and args.admin_password:
        admin = Client(args.url)
        code, txt, _ = admin.req(
            "POST", "/api/login",
            {"username": args.admin_user, "password": args.admin_password}, timeout=30,
        )
        permisos["admin_login"] = code
        if code == 200:
            permisos["admin_inventory"] = admin.req("GET", "/api/inventory", timeout=20)[0]
            permisos["admin_audit"] = admin.req("GET", "/api/admin/audit?limite=5", timeout=20)[0]
            permisos["admin_sesiones"] = admin.req("GET", "/api/admin/sesiones", timeout=20)[0]
            permisos["admin_panel"] = admin.req("GET", "/admin", timeout=20)[0]
        else:
            errores.append(f"admin login: {code} {txt[:120]}")

    esperado = {
        "anon_inventory": 401, "anon_root": 200, "cliente_inventory": 403,
        "cliente_admin": 403, "cliente_chat": 200, "health": 200,
        "admin_inventory": 200, "admin_audit": 200, "admin_sesiones": 200, "admin_panel": 200,
    }
    for clave, valor_esperado in esperado.items():
        if clave in permisos and permisos[clave] != valor_esperado:
            errores.append(f"{clave}: esperado {valor_esperado}, obtenido {permisos[clave]}")
    # 503 es una respuesta controlada ("ocupado"), no una caida del servidor.
    if any(int(c) >= 500 and c != "503" for c in estados):
        errores.append(f"hay respuestas 5xx no controladas: {dict(estados)}")

    resumen = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "url": args.url,
        "usuarios": len(users),
        "consultas_por_usuario": args.requests,
        "total_consultas": len(tareas),
        "estados": dict(estados),
        "respuestas_503_controladas": saturados,
        "latencia_p50_s": round(sorted(latencias)[len(latencias) // 2], 3) if latencias else 0,
        "latencia_p95_s": p95(latencias),
        "permisos": permisos,
        "salud": salud,
        "errores": errores,
        "ok": not errores,
    }
    return resumen


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--users", type=int, default=10)
    ap.add_argument("--requests", type=int, default=1)
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--admin-user", default=os.getenv("ADMIN_USER", ""))
    ap.add_argument("--admin-password", default=os.getenv("ADMIN_PASSWORD", ""))
    args = ap.parse_args()

    resultado = run(args)
    out_dir = ROOT / "tests" / "resultados" / "load"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "load_test.json").write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    print("Reporte:", out_dir / "load_test.json")
    return 0 if resultado.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
