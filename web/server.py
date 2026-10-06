"""Servidor web del asistente (stdlib, sin frameworks).

Expone la interfaz de `static/index.html` y una API JSON minima que conversa
con el agente:

    GET  /               -> interfaz (chat + catalogo)
    GET  /api/health     -> estado del LLM, tools, memoria e indice
    GET  /api/inventory  -> filas del inventario (para la tabla de repuestos)
    POST /api/chat       -> {"message": "...", "session": "..."} -> respuesta del agente
    POST /api/reset      -> limpia la memoria de corto plazo de la sesion

Uso:  python web/server.py  [puerto]
"""
from __future__ import annotations

import json
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.agent import health, run  # noqa: E402  (requiere el root en sys.path)
from agent.memory import reset_session  # noqa: E402
from tools.inventory_lookup import ROOT, load_inventory  # noqa: E402

STATIC_DIR = Path(__file__).resolve().parent / "static"
CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css"}
MAX_BODY = 64 * 1024  # 64KB: el chat no deberia mandar mas que esto


class Handler(BaseHTTPRequestHandler):
    server_version = "RepuestosSur/1.0"

    # -- infra ---------------------------------------------------------------
    def _send(self, status: int, body: bytes, content_type: str):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        if length > MAX_BODY:
            raise ValueError("cuerpo demasiado grande")
        raw = self.rfile.read(length)
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("se esperaba un objeto JSON")
        return data

    def log_message(self, fmt, *args):  # log breve por linea
        sys.stdout.write("%s - %s\n" % (self.address_string(), fmt % args))

    # -- rutas ---------------------------------------------------------------
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            return self._serve_static("index.html")
        if path.startswith("/static/"):
            return self._serve_static(path[len("/static/"):])
        if path == "/api/health":
            try:
                info = health()
                try:
                    from agent.rag import stats

                    info["indice"] = stats()
                except Exception as exc:
                    info["indice"] = {"error": exc.__class__.__name__}
                return self._json(info)
            except Exception as exc:
                return self._json({"error": f"{exc.__class__.__name__}: {exc}"}, 500)
        if path == "/api/inventory":
            try:
                return self._json({"parts": load_inventory()})
            except Exception as exc:
                return self._json({"error": f"{exc.__class__.__name__}: {exc}"}, 500)
        return self._json({"error": "ruta no encontrada"}, 404)

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path not in ("/api/chat", "/api/reset"):
            return self._json({"error": "ruta no encontrada"}, 404)
        try:
            data = self._read_json()
        except Exception as exc:
            return self._json({"error": f"JSON invalido: {exc}"}, 400)

        session = str(data.get("session") or "web")[:64]
        try:
            if path == "/api/reset":
                reset_session(session)
                return self._json({"ok": True, "session": session})

            message = str(data.get("message") or "").strip()
            if not message:
                return self._json({"error": "mensaje vacio"}, 400)
            return self._json(run(message, session_id=session))
        except Exception as exc:
            return self._json({"error": f"{exc.__class__.__name__}: {exc}"}, 500)

    def _serve_static(self, name: str):
        target = (STATIC_DIR / name).resolve()
        if not str(target).startswith(str(STATIC_DIR.resolve())) or not target.is_file():
            return self._json({"error": "archivo no encontrado"}, 404)
        ctype = CONTENT_TYPES.get(target.suffix, "application/octet-stream")
        self._send(200, target.read_bytes(), ctype)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}"
    print(f"Repuestos Sur - asistente IA")
    print(f"Interfaz: {url}  (Ctrl+C para detener)")
    print(f"Raiz del proyecto: {ROOT}")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
        server.server_close()


if __name__ == "__main__":
    main()
