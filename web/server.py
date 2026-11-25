"""Servidor web del asistente (stdlib, sin frameworks).

Rutas publicas:
    GET  /login, /register, /static/*  -> paginas de acceso
    POST /api/login, /api/register     -> sesion / alta de clientes
    GET  /api/health                   -> estado minimo (sin secretos)

Rutas autenticadas (cliente o admin):
    GET  /, /api/me
    POST /api/chat, /api/reset, /api/logout

Rutas solo admin:
    GET  /admin, /api/inventory, /api/admin/usuarios,
         /api/admin/sesiones, /api/admin/audit
    POST /api/admin/usuarios
    PATCH/DELETE /api/admin/usuarios/<id>...
    DELETE /api/admin/sesiones/<token_hash>

Concurrencia: cola acotada de chats + circuit breaker + rate limit por usuario.
Uso:  python web/server.py  [puerto]
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import webbrowser
from collections import deque
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.agent import (  # noqa: E402
    circuit_abierto,
    circuit_reintentar_en,
    health,
    registrar_resultado,
    run,
)
from agent.memory import reset_session  # noqa: E402
from tools.inventory_lookup import ROOT, load_inventory  # noqa: E402
from web import auth  # noqa: E402

STATIC_DIR = Path(__file__).resolve().parent / "static"
CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css"}
MAX_BODY = 64 * 1024
MAX_MESSAGE_CHARS = 4000

MAX_CONCURRENT_CHATS = max(1, int(os.getenv("MAX_CONCURRENT_CHATS") or 3))
CHAT_RATE_LIMIT = max(1, int(os.getenv("CHAT_RATE_LIMIT_PER_MIN") or 20))
WEB_RETRY_WAIT_S = max(0.0, float(os.getenv("WEB_RETRY_WAIT_S") or 5))
CHAT_QUEUE_WAIT_S = max(0.0, float(os.getenv("CHAT_QUEUE_WAIT_S") or 15))
ALLOWED_ORIGIN = (os.getenv("REPUSTOS_ALLOWED_ORIGIN") or "").strip()

_CHAT_SEMAPHORE = threading.BoundedSemaphore(MAX_CONCURRENT_CHATS)
_RATE_LOCK = threading.Lock()
_RATE_BUCKETS: dict[str, deque] = {}
_CSP = (
    "default-src 'self'; style-src 'self' 'unsafe-inline'; "
    "script-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; "
    "form-action 'self'; base-uri 'self'; frame-ancestors 'none'"
)


def _rate_ok(key: str, limit: int, window_s: float = 60) -> bool:
    """Limitador de ventana deslizante en memoria (por usuario/IP)."""
    ahora = time.time()
    with _RATE_LOCK:
        bucket = _RATE_BUCKETS.setdefault(key, deque())
        while bucket and bucket[0] < ahora - window_s:
            bucket.popleft()
        if len(bucket) >= limit:
            return False
        bucket.append(ahora)
        # Evita que el dict crezca sin limite con usuarios que nunca vuelven.
        if len(_RATE_BUCKETS) > 2000:
            for k, v in list(_RATE_BUCKETS.items()):
                if not v or v[-1] < ahora - window_s:
                    _RATE_BUCKETS.pop(k, None)
        return True


class RepuestosHTTPServer(ThreadingHTTPServer):
    daemon_threads = True  # los hilos sobrantes no traban el shutdown
    allow_reuse_address = True
    request_queue_size = 128


class Handler(BaseHTTPRequestHandler):
    server_version = "RepuestosSur/2.0"

    # -- infra ---------------------------------------------------------------
    def _send(self, status: int, body: bytes, content_type: str, extra_headers: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", _CSP)
        self.send_header("Vary", "Origin")
        if ALLOWED_ORIGIN and self.headers.get("Origin") == ALLOWED_ORIGIN:
            self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data, status: int = 200, headers: dict | None = None):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8", headers)

    def _redirect(self, location: str, status: int = 303):
        self.send_response(status)
        self.send_header("Location", location)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _read_json(self) -> dict:
        ctype = (self.headers.get("Content-Type") or "").lower()
        if "application/json" not in ctype:
            raise ValueError("Content-Type debe ser application/json")
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        if length > MAX_BODY:
            raise ValueError("cuerpo demasiado grande")
        data = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("se esperaba un objeto JSON")
        return data

    def log_message(self, fmt, *args):
        sys.stdout.write("%s - %s\n" % (self.address_string(), fmt % args))

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Allow", "GET, POST, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Vary", "Origin")
        if ALLOWED_ORIGIN and self.headers.get("Origin") == ALLOWED_ORIGIN:
            self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
        self.end_headers()

    # -- sesion --------------------------------------------------------------
    def _client_ip(self) -> str:
        forwarded = self.headers.get("X-Forwarded-For") or ""
        if forwarded:
            return forwarded.split(",", 1)[0].strip()[:64]
        return self.address_string()[:64]

    def _ua(self) -> str:
        return (self.headers.get("User-Agent") or "")[:200]

    def _cookie_token(self) -> str | None:
        raw = self.headers.get("Cookie") or ""
        if not raw:
            return None
        try:
            cookie = SimpleCookie()
            cookie.load(raw)
            morsel = cookie.get("rs_sid")
            return morsel.value if morsel else None
        except Exception:
            return None

    def _user(self):
        return auth.get_session(self._cookie_token())

    def _cookie_header(self, token: str) -> str:
        return (
            f"rs_sid={token}; Path=/; Max-Age={auth.SESSION_TTL_S}; "
            "HttpOnly; SameSite=Strict"
            + ("; Secure" if os.getenv("REPUSTOS_HTTPS") == "1" else "")
        )

    def _clear_cookie_header(self) -> str:
        return (
            "rs_sid=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict"
            + ("; Secure" if os.getenv("REPUSTOS_HTTPS") == "1" else "")
        )

    def _deny(self, user, admin: bool = False):
        if user is None:
            self._json({"error": "inicia sesion para continuar"}, 401)
        elif admin:
            self._json({"error": "esta accion requiere rol administrador"}, 403)
        else:
            self._json({"error": "sin permiso"}, 403)

    # -- GET -----------------------------------------------------------------
    def do_GET(self):
        raw_path = self.path.split("?", 1)[0]
        path = unquote(raw_path)
        query = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")

        if path in ("/login", "/login.html"):
            return self._serve_static("login.html")
        if path in ("/register", "/register.html"):
            return self._serve_static("register.html")
        if path.startswith("/static/"):
            return self._serve_static(path[len("/static/"):])
        if path == "/api/health":
            try:
                info = health(detailed=False)
                try:
                    from agent.rag import stats

                    raw = stats()
                    info["indice"] = {
                        "colecciones": {
                            nombre: n
                            for nombre, n in (raw.get("colecciones") or {}).items()
                            if nombre in ("manuales", "inventario")
                        }
                    }
                except Exception:
                    info["indice"] = {"colecciones": {}}
                return self._json(info)
            except Exception as exc:
                return self._json({"error": f"{exc.__class__.__name__}: {exc}"}, 500)

        user = self._user()
        if path in ("/", "/index.html"):
            if user is None:
                return self._redirect("/login")
            return self._serve_static("index.html")
        if path in ("/admin", "/admin.html"):
            if user is None:
                return self._redirect("/login")
            if user["rol"] != "admin":
                return self._json({"error": "requiere rol administrador"}, 403)
            return self._serve_static("admin.html")
        if path.startswith("/api/"):
            if user is None:
                return self._deny(user)
            if path == "/api/me":
                return self._json({
                    "usuario": user["username"], "rol": user["rol"], "email": user.get("email", "")
                })
            if path == "/api/inventory" and user["rol"] == "admin":
                try:
                    return self._json({"parts": load_inventory()})
                except Exception as exc:
                    return self._json({"error": f"{exc.__class__.__name__}: {exc}"}, 500)
            if user["rol"] != "admin":
                return self._deny(user, admin=True)
            if path == "/api/admin/usuarios":
                return self._json({"usuarios": auth.listar_usuarios()})
            if path == "/api/admin/sesiones":
                return self._json({"sesiones": auth.sesiones_activas()})
            if path == "/api/admin/audit":
                return self._json({
                    "eventos": auth.eventos_recientes(
                        limite=int((query.get("limite") or [200])[0]),
                        usuario=(query.get("usuario") or [""])[0],
                        evento=(query.get("evento") or [""])[0],
                    )
                })
        return self._json({"error": "ruta no encontrada"}, 404)

    # -- POST ----------------------------------------------------------------
    def do_POST(self):
        path = self.path.split("?", 1)[0]
        ip, ua = self._client_ip(), self._ua()

        if path in ("/api/login", "/api/register"):
            try:
                data = self._read_json()
            except Exception as exc:
                return self._json({"error": f"JSON invalido: {exc}"}, 400)
            try:
                if path == "/api/login":
                    sesion = auth.login(data.get("username"), data.get("password"), ip, ua)
                    return self._json(
                        {"ok": True, "usuario": sesion["username"], "rol": sesion["rol"]},
                        headers={"Set-Cookie": self._cookie_header(sesion["token"])},
                    )
                else:
                    auth.registrar_usuario_publico(
                        data.get("username"), data.get("password"), ip, ua,
                        email=data.get("email"),
                    )
                    return self._json({"ok": True, "mensaje": "cuenta creada; ya puedes iniciar sesion"})
            except auth.AuthError as exc:
                return self._json({"error": str(exc)}, 401 if path == "/api/login" else 400)
            except Exception as exc:
                return self._json({"error": f"{exc.__class__.__name__}: {exc}"}, 500)

        if path == "/api/logout":
            auth.logout(self._cookie_token(), ip, ua)
            return self._json(
                {"ok": True}, headers={"Set-Cookie": self._clear_cookie_header()}
            )

        user = self._user()
        if path not in ("/api/chat", "/api/reset", "/api/admin/usuarios"):
            return self._deny(user) if user is None else self._json({"error": "ruta no encontrada"}, 404)
        if user is None:
            return self._deny(user)
        if path == "/api/admin/usuarios" and user["rol"] != "admin":
            return self._deny(user, admin=True)

        try:
            data = self._read_json()
        except Exception as exc:
            msg = str(exc)
            if "Content-Type" in msg:
                return self._json({"error": msg}, 415)
            return self._json({"error": f"JSON invalido: {exc}"}, 400)

        if path == "/api/admin/usuarios":
            try:
                if not str(data.get("email") or "").strip():
                    return self._json({"error": "indica un correo electrónico"}, 400)
                creado = auth.crear_usuario(
                    data.get("username"),
                    data.get("password"),
                    data.get("rol") or "cliente",
                    ip,
                    ua,
                    creado_por=user["username"],
                    email=data.get("email"),
                )
                return self._json({"ok": True, "usuario": creado})
            except auth.AuthError as exc:
                return self._json({"error": str(exc)}, 400)
            except Exception as exc:
                return self._json({"error": f"{exc.__class__.__name__}: {exc}"}, 500)

        session = str(data.get("session") or "web")[:64]
        if path == "/api/reset":
            reset_session(f"u{user['id']}:{session}")
            auth.auditoria("chat_reset", usuario=user["username"], rol=user["rol"], ip=ip,
                           user_agent=ua, detalle=session)
            return self._json({"ok": True, "session": session})

        message = str(data.get("message") or "").strip()
        if not message:
            return self._json({"error": "mensaje vacio"}, 400)
        if len(message) > MAX_MESSAGE_CHARS:
            return self._json(
                {"error": f"mensaje demasiado largo (max {MAX_MESSAGE_CHARS} caracteres)"}, 400
            )

        if not _rate_ok(f"chat:u{user['id']}", CHAT_RATE_LIMIT):
            auth.auditoria("rate_limited", usuario=user["username"], rol=user["rol"], ip=ip,
                           user_agent=ua, detalle="limite por usuario")
            return self._json(
                {"error": "demasiadas consultas por minuto; espera un momento", "retry_after": 60},
                429,
            )
        if not _rate_ok(f"chat:ip:{ip}", CHAT_RATE_LIMIT * 3):
            auth.auditoria("rate_limited", usuario=user["username"], rol=user["rol"], ip=ip,
                           user_agent=ua, detalle="limite por IP")
            return self._json({"error": "demasiadas consultas desde esta IP"}, 429)
        if circuit_abierto():
            espera = circuit_reintentar_en()
            return self._json(
                {"error": "servicio de IA en pausa breve por saturacion", "retry_after": espera},
                503,
            )
        # Espera acotada: con 5-10 usuarios se van turnando, pero ningun hilo
        # espera mas de CHAT_QUEUE_WAIT_S (descartar rapido si no da alcance).
        if not _CHAT_SEMAPHORE.acquire(timeout=CHAT_QUEUE_WAIT_S):
            auth.auditoria("saturado", usuario=user["username"], rol=user["rol"], ip=ip,
                           user_agent=ua, detalle="cola de chats llena")
            return self._json(
                {"error": "servidor ocupado; reintenta en unos segundos",
                 "retry_after": int(CHAT_QUEUE_WAIT_S) or 5},
                503,
            )

        try:
            resultado = run(
                message,
                session_id=f"u{user['id']}:{session}",
                max_retry_wait_s=WEB_RETRY_WAIT_S,
                destinatario=user.get("email", ""),
            )
            registrar_resultado(
                bool(resultado.get("rate_limited")), bool(resultado.get("limite_diario"))
            )
            auth.auditoria(
                "chat_request", usuario=user["username"], rol=user["rol"], ip=ip,
                user_agent=ua, detalle=f"chars={len(message)}",
            )
            return self._json(resultado)
        except Exception as exc:
            print(f"[web] error en /api/chat: {exc.__class__.__name__}: {exc}")
            auth.auditoria("chat_error", usuario=user["username"], rol=user["rol"], ip=ip,
                           user_agent=ua, detalle=exc.__class__.__name__)
            return self._json({"error": f"Error interno: {exc.__class__.__name__}"}, 500)
        finally:
            _CHAT_SEMAPHORE.release()

    # -- PATCH / DELETE (admin) ----------------------------------------------
    def do_PATCH(self):
        user = self._user()
        if user is None or user["rol"] != "admin":
            return self._deny(user, admin=True)
        path = self.path.split("?", 1)[0]
        partes = path.strip("/").split("/")
        if len(partes) != 5 or partes[:2] != ["api", "admin"] or partes[2] != "usuarios":
            return self._json({"error": "ruta no encontrada"}, 404)
        try:
            user_id = int(partes[3])
            data = self._read_json()
            if partes[4] == "rol":
                return self._json(auth.cambiar_rol(user_id, data.get("rol"), user["username"],
                                                   self._client_ip(), self._ua()))
            if partes[4] == "activo":
                return self._json(auth.cambiar_activo(user_id, bool(data.get("activo")),
                                                      user["username"], self._client_ip(), self._ua()))
        except auth.AuthError as exc:
            return self._json({"error": str(exc)}, 400)
        except Exception as exc:
            return self._json({"error": f"{exc.__class__.__name__}: {exc}"}, 500)
        return self._json({"error": "ruta no encontrada"}, 404)

    def do_DELETE(self):
        user = self._user()
        if user is None or user["rol"] != "admin":
            return self._deny(user, admin=True)
        path = self.path.split("?", 1)[0]
        partes = path.strip("/").split("/")
        ip, ua = self._client_ip(), self._ua()
        try:
            if len(partes) == 4 and partes[:3] == ["api", "admin", "usuarios"]:
                return self._json(auth.eliminar_usuario(int(partes[3]), user["username"], ip, ua))
            if len(partes) == 5 and partes[:3] == ["api", "admin", "sesiones"]:
                ok = auth.cerrar_sesion(partes[4], user["username"], ip, ua)
                return self._json({"ok": ok})
        except auth.AuthError as exc:
            return self._json({"error": str(exc)}, 400)
        except Exception as exc:
            return self._json({"error": f"{exc.__class__.__name__}: {exc}"}, 500)
        return self._json({"error": "ruta no encontrada"}, 404)

    def _serve_static(self, name: str):
        name = Path(name).name  # solo archivos directos de static/
        target = (STATIC_DIR / name).resolve()
        dad = STATIC_DIR.resolve()
        if (not str(target).startswith(str(dad))) or target.suffix not in CONTENT_TYPES or not target.is_file():
            return self._json({"error": "archivo no encontrado"}, 404)
        self._send(200, target.read_bytes(), CONTENT_TYPES[target.suffix])


def main():
    port_env = os.environ.get("REPUSTOS_PORT") or os.environ.get("PORT")
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    elif port_env:
        port = int(port_env)
    else:
        port = 8000
    host = os.environ.get("REPUSTOS_HOST", "127.0.0.1")

    auth.inicializar()
    auth.ensure_bootstrap_admin()
    try:
        from agent.rag import preload

        preload()
    except Exception as exc:
        print(f"[web] no se pudo precalentar el RAG: {exc.__class__.__name__}: {exc}")

    server = RepuestosHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}"
    print("Repuestos Sur - asistente IA")
    print(f"Interfaz: {url}/login  (Ctrl+C para detener)")
    print(f"Chats concurrentes: {MAX_CONCURRENT_CHATS} | rate limit: {CHAT_RATE_LIMIT}/min por usuario")
    print(f"Raiz del proyecto: {ROOT}")
    if host in ("127.0.0.1", "localhost"):
        try:
            webbrowser.open(f"{url}/login")
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
        server.server_close()


if __name__ == "__main__":
    main()
