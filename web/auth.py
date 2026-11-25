"""Autenticacion, roles, sesiones y auditoria del servidor web.

Todo se guarda en SQLite de la stdlib (``data/internal/auth.db`` por defecto),
asi que no agrega dependencias al proyecto. Diseno:

    usuarios  -> cliente/admin, password hasheada con PBKDF2
    sesiones  -> token aleatorio; en BD solo su SHA-256 (revocables)
    auditoria -> eventos de registro/login/acciones de admin (30 dias)

La contraseña del admin inicial se toma de ``ADMIN_USER`` + ``ADMIN_PASSWORD``
(o ``ADMIN_PASSWORD_HASH``) y solo se crea si no existe ningun admin.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Se calcula aca (y no se importa de tools.inventory_lookup) para que el
# modulo de auth sea independiente del CSV del inventario y pueda usarse en
# pruebas con rutas aisladas sin cargar otros modulos del agente.
ROOT = Path(__file__).resolve().parent.parent

load_dotenv()

AUTH_DB_PATH_RAW = (os.getenv("AUTH_DB_PATH") or "").strip()
AUTH_DB_PATH = (
    Path(AUTH_DB_PATH_RAW)
    if Path(AUTH_DB_PATH_RAW).is_absolute()
    else (ROOT / AUTH_DB_PATH_RAW if AUTH_DB_PATH_RAW else ROOT / "data" / "internal" / "auth.db")
)

SESSION_TTL_S = int(os.getenv("WEB_SESSION_TTL_S") or 8 * 3600)
LOGIN_MAX_ATTEMPTS = int(os.getenv("LOGIN_MAX_ATTEMPTS") or 5)
LOGIN_LOCKOUT_S = int(os.getenv("LOGIN_LOCKOUT_S") or 15 * 60)
REGISTER_MAX_PER_HOUR = int(os.getenv("REGISTER_MAX_PER_HOUR") or 50)
AUDIT_RETENTION_DAYS = int(os.getenv("AUDIT_RETENTION_DAYS") or 30)
PBKDF2_ITERATIONS = 210_000

USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,32}$")
ROLES = ("cliente", "admin")

_WRITE_LOCK = threading.RLock()
_PRUNE_LOCK = threading.Lock()
_last_prune = 0.0

SCHEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    rol           TEXT NOT NULL CHECK (rol IN ('cliente','admin')),
    activo        INTEGER NOT NULL DEFAULT 1,
    creado_en     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sesiones (
    token_hash TEXT PRIMARY KEY,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    creado_en  TEXT NOT NULL,
    creado_ts  REAL NOT NULL,
    expira_ts  REAL NOT NULL,
    ip         TEXT NOT NULL DEFAULT '',
    user_agent TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS auditoria (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         TEXT NOT NULL,
    ts_epoch   REAL NOT NULL,
    usuario    TEXT NOT NULL DEFAULT '',
    rol        TEXT NOT NULL DEFAULT '',
    evento     TEXT NOT NULL,
    ip         TEXT NOT NULL DEFAULT '',
    user_agent TEXT NOT NULL DEFAULT '',
    detalle    TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_sesiones_usuario ON sesiones(usuario_id);
CREATE INDEX IF NOT EXISTS idx_sesiones_expira ON sesiones(expira_ts);
CREATE INDEX IF NOT EXISTS idx_auditoria_ts ON auditoria(ts_epoch);
CREATE INDEX IF NOT EXISTS idx_auditoria_evento ON auditoria(evento);
CREATE INDEX IF NOT EXISTS idx_auditoria_usuario ON auditoria(usuario);
"""


class AuthError(Exception):
    """Error de negocio de autenticacion (se muestra al usuario)."""


@contextmanager
def conexion():
    """Conexion corta a la BD de auth (una por operacion, segura con hilos)."""
    AUTH_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(AUTH_DB_PATH), timeout=15, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=15000")
        conn.execute("PRAGMA foreign_keys=ON")
        yield conn
    finally:
        conn.close()


def inicializar() -> None:
    with _WRITE_LOCK, conexion() as conn:
        conn.executescript(SCHEMA)


# --------------------------------------------------------------------------
# Passwords
# --------------------------------------------------------------------------
def hash_password(password: str) -> str:
    if not isinstance(password, str) or len(password) < 10:
        raise AuthError("la contraseña debe tener al menos 10 caracteres")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iteraciones, salt_hex, hash_hex = stored.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iteraciones)
        )
        return hmac.compare_digest(digest.hex(), hash_hex)
    except Exception:
        return False


def validar_username(username: str) -> str:
    user = (username or "").strip()
    if not USERNAME_RE.match(user):
        raise AuthError("usuario: 3-32 caracteres, solo letras, numeros, punto, guion o guion bajo")
    return user


def validar_rol(rol: str) -> str:
    rol = (rol or "").strip().lower()
    if rol not in ROLES:
        raise AuthError("rol invalido (debe ser 'cliente' o 'admin')")
    return rol


# --------------------------------------------------------------------------
# Auditoria
# --------------------------------------------------------------------------
def _podar(conn: sqlite3.Connection, forzar: bool = False) -> None:
    """Borra eventos mas viejos que AUDIT_RETENTION_DAYS (como maximo 1 vez/hora)."""
    global _last_prune
    ahora = time.time()
    if not forzar and ahora - _last_prune < 3600:
        return
    with _PRUNE_LOCK:
        conn.execute(
            "DELETE FROM auditoria WHERE ts_epoch < ?",
            (ahora - AUDIT_RETENTION_DAYS * 86400,),
        )
        conn.execute("DELETE FROM sesiones WHERE expira_ts < ?", (ahora,))
        _last_prune = ahora


def auditoria(
    evento: str,
    usuario: str = "",
    rol: str = "",
    ip: str = "",
    user_agent: str = "",
    detalle: str = "",
    conn: sqlite3.Connection | None = None,
) -> None:
    """Escribe un evento de auditoria. Nunca guarda passwords ni tokens."""
    ahora = time.time()
    fila = (
        datetime.fromtimestamp(ahora).isoformat(timespec="seconds"),
        ahora,
        (usuario or "")[:64],
        (rol or "")[:16],
        evento[:48],
        (ip or "")[:64],
        (user_agent or "")[:200],
        (detalle or "")[:300],
    )
    if conn is not None:
        conn.execute(
            "INSERT INTO auditoria (ts, ts_epoch, usuario, rol, evento, ip, user_agent, detalle) "
            "VALUES (?,?,?,?,?,?,?,?)",
            fila,
        )
        return
    with _WRITE_LOCK, conexion() as c:
        c.execute(
            "INSERT INTO auditoria (ts, ts_epoch, usuario, rol, evento, ip, user_agent, detalle) "
            "VALUES (?,?,?,?,?,?,?,?)",
            fila,
        )
        _podar(c)


def eventos_recientes(limite: int = 200, usuario: str = "", evento: str = "") -> list[dict]:
    inicializar()
    limite = max(1, min(int(limite or 200), 500))
    sql = "SELECT ts, usuario, rol, evento, ip, user_agent, detalle FROM auditoria WHERE 1=1"
    args: list = []
    if usuario:
        sql += " AND usuario LIKE ?"
        args.append(f"%{usuario}%")
    if evento:
        sql += " AND evento = ?"
        args.append(evento)
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(limite)
    with conexion() as conn:
        _podar(conn)
        filas = conn.execute(sql, args).fetchall()
    return [dict(f) for f in filas]


# --------------------------------------------------------------------------
# Bootstrap / usuarios
# --------------------------------------------------------------------------
def ensure_bootstrap_admin() -> bool:
    """Crea el admin inicial desde .env solo si todavia no hay ningun admin."""
    inicializar()
    user = (os.getenv("ADMIN_USER") or "").strip()
    password = os.getenv("ADMIN_PASSWORD") or ""
    password_hash = (os.getenv("ADMIN_PASSWORD_HASH") or "").strip()
    with _WRITE_LOCK, conexion() as conn:
        hay_admin = conn.execute("SELECT 1 FROM usuarios WHERE rol='admin' LIMIT 1").fetchone()
        if hay_admin:
            return False
        if not user or not (password or password_hash):
            print(
                "[auth] No hay admin: define ADMIN_USER y ADMIN_PASSWORD "
                "(o ADMIN_PASSWORD_HASH) en .env y reinicia."
            )
            return False
        try:
            user = validar_username(user)
            stored = password_hash if password_hash else hash_password(password)
        except AuthError as exc:
            print(f"[auth] No se pudo crear el admin inicial: {exc}")
            return False
        conn.execute(
            "INSERT OR IGNORE INTO usuarios (username, password_hash, rol, activo, creado_en) "
            "VALUES (?,?,?,1,?)",
            (user, stored, "admin", datetime.now().isoformat(timespec="seconds")),
        )
        auditoria("crear_admin", usuario=user, rol="admin", detalle="bootstrap desde .env", conn=conn)
    return True


def listar_usuarios() -> list[dict]:
    inicializar()
    with conexion() as conn:
        filas = conn.execute(
            "SELECT id, username, rol, activo, creado_en FROM usuarios ORDER BY id"
        ).fetchall()
    out = []
    for f in filas:
        d = dict(f)
        d["activo"] = bool(d["activo"])
        out.append(d)
    return out


def crear_usuario(
    username: str,
    password: str,
    rol: str = "cliente",
    ip: str = "",
    user_agent: str = "",
    creado_por: str = "",
) -> dict:
    user = validar_username(username)
    rol = validar_rol(rol)
    stored = hash_password(password)
    inicializar()
    with _WRITE_LOCK, conexion() as conn:
        existe = conn.execute("SELECT 1 FROM usuarios WHERE username = ?", (user,)).fetchone()
        if existe:
            auditoria("crear_usuario_fail", usuario=user, ip=ip, user_agent=user_agent,
                      detalle="usuario ya existe", conn=conn)
            raise AuthError("ese usuario ya existe")
        cur = conn.execute(
            "INSERT INTO usuarios (username, password_hash, rol, activo, creado_en) "
            "VALUES (?,?,?,1,?)",
            (user, stored, rol, datetime.now().isoformat(timespec="seconds")),
        )
        evento = "crear_usuario" if creado_por else "registro_ok"
        auditoria(
            evento,
            usuario=creado_por or user,
            rol="admin" if creado_por else rol,
            ip=ip,
            user_agent=user_agent,
            detalle=f"nuevo usuario: {user} ({rol})",
            conn=conn,
        )
        uid = int(cur.lastrowid)
    return {"id": uid, "username": user, "rol": rol, "activo": True}


def registrar_usuario_publico(username: str, password: str, ip: str, user_agent: str) -> dict:
    """Alta abierta: cualquier companero se crea una cuenta de cliente."""
    inicializar()
    ahora = time.time()
    with _WRITE_LOCK, conexion() as conn:
        usados = conn.execute(
            "SELECT COUNT(*) AS n FROM auditoria "
            "WHERE ip = ? AND evento IN ('registro_ok','registro_bloqueado') AND ts_epoch > ?",
            ((ip or "")[:64], ahora - 3600),
        ).fetchone()["n"]
        if usados >= REGISTER_MAX_PER_HOUR:
            auditoria("registro_bloqueado", ip=ip, user_agent=user_agent,
                      detalle="limite de registros por hora", conn=conn)
            raise AuthError("demasiados registros desde esta IP; intenta mas tarde")
    return crear_usuario(username, password, "cliente", ip, user_agent)


def cambiar_rol(user_id: int, rol: str, admin_user: str, ip: str = "", user_agent: str = "") -> dict:
    rol = validar_rol(rol)
    inicializar()
    with _WRITE_LOCK, conexion() as conn:
        fila = conn.execute("SELECT username FROM usuarios WHERE id = ?", (int(user_id),)).fetchone()
        if fila is None:
            raise AuthError("usuario no encontrado")
        conn.execute("UPDATE usuarios SET rol = ? WHERE id = ?", (rol, int(user_id)))
        auditoria("cambio_rol", usuario=admin_user, rol="admin", ip=ip, user_agent=user_agent,
                  detalle=f"{fila['username']} -> {rol}", conn=conn)
    return {"id": int(user_id), "rol": rol}


def cambiar_activo(user_id: int, activo: bool, admin_user: str, ip: str = "", user_agent: str = "") -> dict:
    inicializar()
    with _WRITE_LOCK, conexion() as conn:
        fila = conn.execute("SELECT username FROM usuarios WHERE id = ?", (int(user_id),)).fetchone()
        if fila is None:
            raise AuthError("usuario no encontrado")
        conn.execute("UPDATE usuarios SET activo = ? WHERE id = ?", (1 if activo else 0, int(user_id)))
        if not activo:
            conn.execute("DELETE FROM sesiones WHERE usuario_id = ?", (int(user_id),))
        auditoria("cambio_estado", usuario=admin_user, rol="admin", ip=ip, user_agent=user_agent,
                  detalle=f"{fila['username']} -> {'activo' if activo else 'inactivo'}", conn=conn)
    return {"id": int(user_id), "activo": bool(activo)}


def eliminar_usuario(user_id: int, admin_user: str, ip: str = "", user_agent: str = "") -> dict:
    inicializar()
    with _WRITE_LOCK, conexion() as conn:
        fila = conn.execute("SELECT username, rol FROM usuarios WHERE id = ?", (int(user_id),)).fetchone()
        if fila is None:
            raise AuthError("usuario no encontrado")
        nombre = fila["username"]
        conn.execute("DELETE FROM usuarios WHERE id = ?", (int(user_id),))  # cascada: sesiones
        auditoria("eliminar_usuario", usuario=admin_user, rol="admin", ip=ip, user_agent=user_agent,
                  detalle=f"eliminado: {nombre} ({fila['rol']})", conn=conn)
    return {"id": int(user_id), "username": nombre}


# --------------------------------------------------------------------------
# Sesiones
# --------------------------------------------------------------------------
def login(username: str, password: str, ip: str = "", user_agent: str = "") -> dict:
    user = (username or "").strip()
    inicializar()
    ahora = time.time()
    with _WRITE_LOCK, conexion() as conn:
        fallos = conn.execute(
            "SELECT COUNT(*) AS n FROM auditoria "
            "WHERE evento = 'login_fail' AND usuario = ? AND ts_epoch > ?",
            (user, ahora - LOGIN_LOCKOUT_S),
        ).fetchone()["n"]
        if fallos >= LOGIN_MAX_ATTEMPTS:
            auditoria("login_bloqueado", usuario=user, ip=ip, user_agent=user_agent,
                      detalle=f"{LOGIN_MAX_ATTEMPTS} intentos fallidos", conn=conn)
            raise AuthError("demasiados intentos fallidos; espera unos minutos")

        fila = conn.execute(
            "SELECT id, username, password_hash, rol, activo FROM usuarios WHERE username = ?",
            (user,),
        ).fetchone()
        if fila is None or not fila["activo"] or not verify_password(password or "", fila["password_hash"]):
            auditoria("login_fail", usuario=user, ip=ip, user_agent=user_agent, conn=conn)
            raise AuthError("usuario o contraseña incorrectos")

        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        conn.execute(
            "INSERT INTO sesiones (token_hash, usuario_id, creado_en, creado_ts, expira_ts, ip, user_agent) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                token_hash,
                fila["id"],
                datetime.now().isoformat(timespec="seconds"),
                ahora,
                ahora + SESSION_TTL_S,
                (ip or "")[:64],
                (user_agent or "")[:200],
            ),
        )
        auditoria("login_ok", usuario=fila["username"], rol=fila["rol"], ip=ip,
                  user_agent=user_agent, conn=conn)
    return {"token": token, "username": fila["username"], "rol": fila["rol"]}


def get_session(token: str | None) -> dict | None:
    if not token:
        return None
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    inicializar()
    ahora = time.time()
    with conexion() as conn:
        fila = conn.execute(
            "SELECT u.id, u.username, u.rol, u.activo, s.expira_ts, s.creado_en, s.ip "
            "FROM sesiones s JOIN usuarios u ON u.id = s.usuario_id "
            "WHERE s.token_hash = ?",
            (token_hash,),
        ).fetchone()
        if fila is None:
            return None
        if fila["expira_ts"] < ahora or not fila["activo"]:
            conn.execute("DELETE FROM sesiones WHERE token_hash = ?", (token_hash,))
            return None
    return {
        "id": fila["id"],
        "username": fila["username"],
        "rol": fila["rol"],
        "token_hash": token_hash,
        "creado_en": fila["creado_en"],
        "ip": fila["ip"],
        "expira_ts": fila["expira_ts"],
    }


def logout(token: str | None, ip: str = "", user_agent: str = "") -> bool:
    if not token:
        return False
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    inicializar()
    with _WRITE_LOCK, conexion() as conn:
        fila = conn.execute(
            "SELECT u.username, u.rol FROM sesiones s JOIN usuarios u ON u.id = s.usuario_id "
            "WHERE s.token_hash = ?",
            (token_hash,),
        ).fetchone()
        conn.execute("DELETE FROM sesiones WHERE token_hash = ?", (token_hash,))
        if fila:
            auditoria("logout", usuario=fila["username"], rol=fila["rol"], ip=ip,
                      user_agent=user_agent, conn=conn)
    return True


def sesiones_activas() -> list[dict]:
    inicializar()
    ahora = time.time()
    with conexion() as conn:
        conn.execute("DELETE FROM sesiones WHERE expira_ts < ?", (ahora,))
        filas = conn.execute(
            "SELECT s.token_hash, s.creado_en, s.expira_ts, s.ip, u.id AS usuario_id, "
            "u.username, u.rol FROM sesiones s "
            "JOIN usuarios u ON u.id = s.usuario_id ORDER BY s.creado_ts DESC"
        ).fetchall()
    return [
        {
            "token_hash": f["token_hash"][:16],
            "usuario_id": f["usuario_id"],
            "username": f["username"],
            "rol": f["rol"],
            "creado_en": f["creado_en"],
            "expira_en": datetime.fromtimestamp(f["expira_ts"]).isoformat(timespec="seconds"),
            "ip": f["ip"],
        }
        for f in filas
    ]


def cerrar_sesion(token_hash_prefix: str, admin_user: str, ip: str = "", user_agent: str = "") -> bool:
    """Cierra una sesion desde el panel de admin (acepta los 16 chars mostrados)."""
    inicializar()
    with _WRITE_LOCK, conexion() as conn:
        fila = conn.execute(
            "SELECT s.token_hash, u.username FROM sesiones s JOIN usuarios u ON u.id = s.usuario_id "
            "WHERE s.token_hash LIKE ?",
            (f"{token_hash_prefix}%",),
        ).fetchone()
        if fila is None:
            return False
        conn.execute("DELETE FROM sesiones WHERE token_hash = ?", (fila["token_hash"],))
        auditoria("cerrar_sesion_admin", usuario=admin_user, rol="admin", ip=ip,
                  user_agent=user_agent, detalle=f"sesion cerrada: {fila['username']}", conn=conn)
    return True
