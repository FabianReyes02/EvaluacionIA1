"""Pruebas de degradación elegante y límites de memoria (sin LLM).

No gastan tokens: verifican que la saturación devuelve una respuesta útil y
que las estructuras en memoria no crecen sin límite.
"""
from __future__ import annotations

import json
import sys
import threading
import urllib.error
import urllib.request
import uuid
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.request import HTTPCookieProcessor, Request, build_opener

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import memory  # noqa: E402
from agent.agent import fallback_result  # noqa: E402


def test_saturacion_devuelve_respuesta_util_sin_estado_de_error():
    r = fallback_result(
        "¿qué alternador para Suzuki Swift 2015?", session_id="test-saturacion", retry_after=5
    )
    assert r["used_llm"] is False
    assert r["modo_sin_ia"] is True
    assert r["saturado"] is True
    assert r["retry_after"] == 5
    assert "ALT-01" in r["respuesta"]
    assert isinstance(r["guardrails"], list)


def test_sesiones_caducan_y_se_acotan_por_lru(monkeypatch):
    memory._SESSIONS.clear()
    monkeypatch.setattr(memory, "SESSION_TTL_S", 1)
    monkeypatch.setattr(memory, "MAX_SESSIONS", 2)
    try:
        memory.get_session("a")
        b = memory.get_session("b")
        assert set(memory._SESSIONS) == {"a", "b"}

        b.last_used = 0  # sesión inactiva: debe expirar
        memory.get_session("c")
        assert "b" not in memory._SESSIONS

        memory.get_session("d")  # se Descarta la menos usada ("a")
        assert set(memory._SESSIONS) == {"c", "d"}
    finally:
        memory._SESSIONS.clear()


def test_memoria_larga_no_crece_sin_limite(monkeypatch, tmp_path):
    # Se reemplaza el módulo RAG para no depender de Chroma en esta prueba.
    import types

    rag_falso = types.ModuleType("agent.rag")
    rag_falso.add_documents = lambda **kwargs: None
    monkeypatch.setitem(sys.modules, "agent.rag", rag_falso)
    monkeypatch.setattr(memory, "MEMORY_DIR", tmp_path)
    monkeypatch.setattr(memory, "MEMORY_FILE", tmp_path / "memoria.jsonl")
    monkeypatch.setattr(memory, "MAX_LONG_TERM_REGISTROS", 3)
    for i in range(5):
        memory.LongTermMemory.record(f"dato {i}", categoria="prueba")
    lineas = (tmp_path / "memoria.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lineas) == 3
    assert "dato 4" in lineas[-1]


def test_memoria_larga_esta_particionada_por_usuario(monkeypatch, tmp_path):
    import types

    rag_falso = types.ModuleType("agent.rag")
    rag_falso.add_documents = lambda **kwargs: None
    monkeypatch.setitem(sys.modules, "agent.rag", rag_falso)
    monkeypatch.setattr(memory, "MEMORY_DIR", tmp_path)
    monkeypatch.setattr(memory, "MEMORY_FILE", tmp_path / "memoria.jsonl")

    t1 = memory.usar_usuario(11)
    memory.LongTermMemory.record("secreto de once", categoria="vehiculo")
    memory.liberar_usuario(t1)
    t2 = memory.usar_usuario(22)
    memory.LongTermMemory.record("dato de veintidos", categoria="vehiculo")
    memory.liberar_usuario(t2)

    uno = (tmp_path / "memoria_11.jsonl").read_text(encoding="utf-8")
    dos = (tmp_path / "memoria_22.jsonl").read_text(encoding="utf-8")
    assert "secreto de once" in uno and "dato de veintidos" not in uno
    assert "dato de veintidos" in dos and "secreto de once" not in dos


def test_chat_con_circuit_abierto_responde_200_y_no_503(monkeypatch):
    from web import server as webserver

    webserver.auth.inicializar()
    monkeypatch.setattr(webserver, "circuit_abierto", lambda: True)
    monkeypatch.setattr(webserver, "circuit_reintentar_en", lambda: 7)
    webserver._READY.set()
    httpd = webserver.RepuestosHTTPServer(("127.0.0.1", 0), webserver.Handler)
    hilo = threading.Thread(target=httpd.serve_forever, daemon=True)
    hilo.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(jar))

    def req(path, body=None):
        datos = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"} if datos else {}
        r = Request(base + path, data=datos, headers=headers, method="POST" if datos else "GET")
        try:
            with opener.open(r, timeout=20) as resp:
                return resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()[:200]

    try:
        user = "sat_" + uuid.uuid4().hex[:8]
        req("/api/register", {"username": user, "password": "ClaveSaturacion123!", "email": "sat@lab"})
        req("/api/login", {"username": user, "password": "ClaveSaturacion123!"})
        code, data = req("/api/chat", {"message": "Suzuki Swift 2015", "session": "sat"})
        assert code == 200
        assert data["saturado"] is True and data["retry_after"] == 7
        assert "ALT-01" in data["respuesta"]
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_csp_por_nonce_y_origen_cross_site_rechazado(monkeypatch):
    from web import server as webserver

    webserver.auth.inicializar()
    webserver._READY.set()
    httpd = webserver.RepuestosHTTPServer(("127.0.0.1", 0), webserver.Handler)
    hilo = threading.Thread(target=httpd.serve_forever, daemon=True)
    hilo.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    opener = build_opener()

    def req(path, method="GET", headers=None, body=None):
        r = Request(base + path, data=body, headers=headers or {}, method=method)
        try:
            with opener.open(r, timeout=20) as resp:
                return resp.status, resp.headers, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()

    try:
        code, headers, body = req("/login")
        csp = headers.get("Content-Security-Policy", "")
        assert code == 200
        assert "nonce-" in csp and "unsafe-inline" not in csp
        html = body.decode("utf-8")
        assert html.count("nonce=") >= 2  # <style> y <script>

        code, _, _ = req(
            "/api/login", "POST",
            {"Content-Type": "application/json", "Origin": "http://evil.example"},
            b'{"username":"x","password":"y"}',
        )
        assert code == 403
    finally:
        httpd.shutdown()
        httpd.server_close()
