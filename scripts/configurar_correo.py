"""Configura las credenciales SMTP de Gmail en el archivo ``.env``.

Uso::

    .\\.venv\\Scripts\\python.exe scripts\\configurar_correo.py

Pide la cuenta de Gmail y la contrasena de aplicacion (oculta en pantalla),
reescribe el bloque de correo de ``.env`` sin tocar el resto de las variables
y al final verifica el **login SMTP sin enviar ningun mensaje**.

La contrasena de aplicacion de Google se muestra como ``abcd efgh ijkl mnop``:
el script le quita los espacios, porque el login falla si se cuelan.
"""
from __future__ import annotations

import getpass
import re
import smtplib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"

HEADER = (
    "# ---------------------------------------------------------------------------\n"
    "# Envio de cotizaciones por correo (tool enviar_cotizacion_email)\n"
    "# ---------------------------------------------------------------------------\n"
)

# Variables que administra este script (se reescriben completas, sin duplicados).
CLAVES = (
    "EMAIL_MODE",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_TLS",
    "SMTP_SSL",
    "SMTP_USER",
    "SMTP_PASSWORD",
    "EMAIL_FROM",
    "EMAIL_TIMEOUT_S",
    "EMAIL_DOMAINS_ALLOWLIST",
)

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def leer_env() -> dict[str, str]:
    """Lee .env como dict (ignora comentarios y lineas vacias)."""
    valores: dict[str, str] = {}
    if not ENV.exists():
        return valores
    for linea in ENV.read_text(encoding="utf-8").splitlines():
        if linea.strip().startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        valores[clave.strip()] = valor.strip().strip('"').strip("'")
    return valores


def escribir_env(nuevos: dict[str, str]) -> None:
    """Reescribe las claves administradas conservando el resto del .env."""
    base = ENV.read_text(encoding="utf-8").splitlines() if ENV.exists() else [""]
    if not any(linea.strip() for linea in base) and ENV_EXAMPLE.exists():
        base = ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()

    conservadas: list[str] = []
    for linea in base:
        if "=" in linea and not linea.strip().startswith("#"):
            clave = linea.split("=", 1)[0].strip()
            if clave in CLAVES:
                continue  # se reescribe abajo
        conservadas.append(linea)

    while conservadas and not conservadas[-1].strip():
        conservadas.pop()

    bloque = [HEADER.rstrip("\n")]
    bloque += [f'{clave}="{valor}"' for clave, valor in nuevos.items()]

    ENV.write_text("\n".join(conservadas + [""] + bloque) + "\n", encoding="utf-8")


def probar_login(host: str, puerto: int, tls: bool, ssl: bool, user: str, password: str) -> bool:
    """Verifica las credenciales SMTP. No envia ningun correo."""
    print(f"\nProbando login en {host}:{puerto} (SSL={ssl}, STARTTLS={tls}) ...")
    try:
        if ssl:
            servidor = smtplib.SMTP_SSL(host, puerto, timeout=20)
        else:
            servidor = smtplib.SMTP(host, puerto, timeout=20)
        try:
            servidor.ehlo()
            if tls and not ssl:
                servidor.starttls()
                servidor.ehlo()
            servidor.login(user, password)
        finally:
            try:
                servidor.quit()
            except Exception:
                pass
    except smtplib.SMTPAuthenticationError as exc:
        print(f"[ERROR] El servidor rechazo las credenciales: {exc.smtp_code} {exc.smtp_error!r}")
        print("        Revisa que sea una contrasena de APLICACION (16 caracteres),")
        print("        que la verificacion en 2 pasos este activa y que el usuario")
        print("        sea la cuenta completa (algo@gmail.com).")
        return False
    except Exception as exc:
        print(f"[ERROR] No se pudo conectar: {exc.__class__.__name__}: {exc}")
        print("        Si es un timeout, prueba el puerto 465 con SSL=1 y TLS=0.")
        return False
    print("[OK] Login SMTP correcto. Las credenciales sirven para enviar.")
    return True


def main() -> int:
    actual = leer_env()

    print("Configuracion del correo de Repuestos Sur")
    print("(Enter para aceptar el valor entre corchetes)\n")

    sugerido = actual.get("SMTP_USER", "")
    user = input(f"Cuenta de Gmail [{sugerido or 'tu.cuenta@gmail.com'}]: ").strip()
    user = user or sugerido or "tu.cuenta@gmail.com"
    if not EMAIL_RE.match(user):
        print(f"[ERROR] '{user}' no parece una direccion valida.")
        return 1

    print("\nContrasena de APLICACION de Google (no se muestra al escribir).")
    print("Generalas en: Cuenta de Google > Seguridad > Contrasenas de aplicaciones")
    password = getpass.getpass("Contrasena de aplicacion: ")
    password = "".join(password.split())  # Google la muestra con espacios
    if len(password) < 8:
        print("[ERROR] La contrasena parece incompleta.")
        return 1

    nuevos = {
        "EMAIL_MODE": "smtp",
        "SMTP_HOST": actual.get("SMTP_HOST") or "smtp.gmail.com",
        "SMTP_PORT": actual.get("SMTP_PORT") or "587",
        "SMTP_TLS": actual.get("SMTP_TLS") or "1",
        "SMTP_SSL": actual.get("SMTP_SSL") or "0",
        "SMTP_USER": user,
        "SMTP_PASSWORD": password,
        "EMAIL_FROM": actual.get("EMAIL_FROM") or "Repuestos Sur",
        "EMAIL_TIMEOUT_S": actual.get("EMAIL_TIMEOUT_S") or "15",
        "EMAIL_DOMAINS_ALLOWLIST": actual.get("EMAIL_DOMAINS_ALLOWLIST", ""),
    }
    escribir_env(nuevos)
    print(f"\n[OK] Bloque de correo escrito en {ENV}")
    print(f"     Remitente: {nuevos['EMAIL_FROM']} <{user}>")

    ok = probar_login(
        nuevos["SMTP_HOST"],
        int(nuevos["SMTP_PORT"]),
        nuevos["SMTP_TLS"].lower() not in ("0", "false", "no"),
        nuevos["SMTP_SSL"].lower() in ("1", "true", "yes"),
        user,
        password,
    )
    if ok:
        print("\nSiguiente paso: manda un correo de prueba a tu propia casilla:")
        print(f'  .\\.venv\\Scripts\\python.exe scripts\\test_email.py --enviar {user}')
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
