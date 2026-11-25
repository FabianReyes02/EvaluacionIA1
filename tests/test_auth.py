"""Pruebas de autenticacion, roles, sesiones y auditoria (sin LLM).

No gastan tokens: usan una BD de auth temporal y el modulo web.auth directo.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="repuestos_auth_"))
os.environ["AUTH_DB_PATH"] = str(TMP / "auth_test.db")
os.environ["ADMIN_USER"] = "admin_prueba"
os.environ["ADMIN_PASSWORD"] = "ClavePrueba123!"
os.environ["WEB_SESSION_TTL_S"] = "3600"
os.environ["LOGIN_MAX_ATTEMPTS"] = "3"
os.environ["LOGIN_LOCKOUT_S"] = "900"
os.environ["AUDIT_RETENTION_DAYS"] = "30"

from web import auth  # noqa: E402


def _limpiar():
    for sufijo in ("", "-wal", "-shm"):
        p = Path(str(TMP / "auth_test.db") + sufijo)
        if p.exists():
            p.unlink()
    auth.inicializar()


def test_password_se_hashea_y_no_guarda_texto():
    _limpiar()
    stored = auth.hash_password("ClaveSuperSecreta123")
    assert stored.startswith("pbkdf2_sha256$")
    assert "ClaveSuperSecreta123" not in stored
    assert auth.verify_password("ClaveSuperSecreta123", stored)
    assert not auth.verify_password("otra", stored)


def test_bootstrap_admin_desde_env():
    _limpiar()
    assert auth.ensure_bootstrap_admin() is True
    usuarios = auth.listar_usuarios()
    assert any(u["username"] == "admin_prueba" and u["rol"] == "admin" for u in usuarios)
    # No se crea dos veces.
    assert auth.ensure_bootstrap_admin() is False


def test_registro_abierto_crea_cliente_y_login():
    _limpiar()
    auth.crear_usuario("admin_prueba", "ClavePrueba123!", "admin")
    nuevo = auth.registrar_usuario_publico(
        "companero", "ClaveCompanero123!", "10.0.0.1", "pytest", email="companero@lab"
    )
    assert nuevo["rol"] == "cliente" and nuevo["activo"] is True
    sesion = auth.login("companero", "ClaveCompanero123!", "10.0.0.1", "pytest")
    assert sesion["rol"] == "cliente" and len(sesion["token"]) > 30
    user = auth.get_session(sesion["token"])
    assert user["username"] == "companero"
    assert auth.logout(sesion["token"]) is True
    assert auth.get_session(sesion["token"]) is None


def test_login_rechaza_clave_mala_y_bloquea_tras_intentos():
    _limpiar()
    auth.crear_usuario("admin_prueba", "ClavePrueba123!", "admin")
    for _ in range(3):
        try:
            auth.login("admin_prueba", "mala", "10.0.0.2", "pytest")
        except auth.AuthError:
            pass
    try:
        auth.login("admin_prueba", "ClavePrueba123!", "10.0.0.2", "pytest")
        raise AssertionError("debió quedar bloqueado")
    except auth.AuthError as exc:
        assert "intentos fallidos" in str(exc)
    eventos = auth.eventos_recientes(usuario="admin_prueba")
    assert any(e["evento"] == "login_fail" for e in eventos)
    assert any(e["evento"] == "login_bloqueado" for e in eventos)


def test_admin_puede_ver_y_cerrar_sesiones_y_eliminar_usuarios():
    _limpiar()
    auth.crear_usuario("admin_prueba", "ClavePrueba123!", "admin")
    auth.registrar_usuario_publico(
        "cliente1", "ClaveCliente123!", "10.0.0.3", "pytest", email="cliente1@lab"
    )
    s = auth.login("cliente1", "ClaveCliente123!", "10.0.0.3", "pytest")
    sesiones = auth.sesiones_activas()
    assert len(sesiones) == 1 and sesiones[0]["username"] == "cliente1"
    hash_corto = sesiones[0]["token_hash"]
    assert auth.cerrar_sesion(hash_corto, "admin_prueba") is True
    assert auth.get_session(s["token"]) is None

    uid = next(u["id"] for u in auth.listar_usuarios() if u["username"] == "cliente1")
    assert auth.eliminar_usuario(uid, "admin_prueba")["username"] == "cliente1"
    assert all(u["username"] != "cliente1" for u in auth.listar_usuarios())
    eventos = auth.eventos_recientes(evento="eliminar_usuario")
    assert eventos and eventos[0]["usuario"] == "admin_prueba"


def test_cambio_de_rol_y_auditoria_no_guarda_passwords():
    _limpiar()
    auth.crear_usuario("admin_prueba", "ClavePrueba123!", "admin")
    u = auth.registrar_usuario_publico(
        "cliente2", "ClaveCliente123!", "10.0.0.4", "pytest", email="cliente2@lab"
    )
    auth.cambiar_rol(u["id"], "admin", "admin_prueba")
    assert any(x["rol"] == "admin" for x in auth.listar_usuarios() if x["username"] == "cliente2")
    texto = str(auth.eventos_recientes(limite=500))
    assert "ClaveCliente123!" not in texto
    assert "ClavePrueba123!" not in texto


def test_correo_de_registro_se_guarda_y_expone_en_la_sesion():
    _limpiar()
    auth.crear_usuario("admin_prueba", "ClavePrueba123!", "admin")
    nuevo = auth.registrar_usuario_publico(
        "probador", "ClaveProbador123!", "10.0.0.9", "pytest", email="probador1@lab"
    )
    assert nuevo["email"] == "probador1@lab"
    assert any(u["email"] == "probador1@lab" for u in auth.listar_usuarios())
    sesion = auth.login("probador", "ClaveProbador123!", "10.0.0.9", "pytest")
    assert sesion["email"] == "probador1@lab"
    assert auth.get_session(sesion["token"])["email"] == "probador1@lab"


def test_registro_exige_correo_y_acepta_direcciones_de_prueba():
    _limpiar()
    auth.crear_usuario("admin_prueba", "ClavePrueba123!", "admin")
    assert auth.validar_email_registro("probador1@lab") == "probador1@lab"
    for correo in ("", "sin-arroba", "a@b@c", "a b@c", "a@<b>"):
        try:
            auth.validar_email_registro(correo)
            raise AssertionError(f"debió rechazar {correo!r}")
        except auth.AuthError:
            pass
    try:
        auth.registrar_usuario_publico("sinmail", "ClaveSinMail123!", "10.0.0.9", "pytest")
        raise AssertionError("el registro público debió exigir correo")
    except auth.AuthError as exc:
        assert "correo" in str(exc).lower()


def test_migracion_de_bd_antigua_anade_la_columna_email():
    _limpiar()
    with auth.conexion() as conn:
        conn.execute("DROP TABLE usuarios")
        conn.execute(
            "CREATE TABLE usuarios ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, "
            "rol TEXT NOT NULL CHECK (rol IN ('cliente','admin')), "
            "activo INTEGER NOT NULL DEFAULT 1, creado_en TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO usuarios (username, password_hash, rol, activo, creado_en) "
            "VALUES ('viejo', 'x', 'cliente', 1, '2026-01-01')"
        )
    auth.inicializar()  # migra sin perder al usuario existente
    assert any(u["username"] == "viejo" and u["email"] == "" for u in auth.listar_usuarios())
    auth.inicializar()  # idempotente
    assert auth.validar_email_registro("nuevo@lab") == "nuevo@lab"
