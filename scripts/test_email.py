"""Prueba el envio de cotizaciones por correo, sin pasar por el LLM.

Uso::

    # 1) Verifica configuracion y credenciales SMTP (NO envia nada)
    .\\.venv\\Scripts\\python.exe scripts\\test_email.py

    # 2) Envia una cotizacion real de prueba a tu propia casilla
    .\\.venv\\Scripts\\python.exe scripts\\test_email.py --enviar tu.cuenta@gmail.com

    # 3) Fuerza el modo dry-run (deja el .eml con el PDF adjunto, no sale a internet)
    .\\.venv\\Scripts\\python.exe scripts\\test_email.py --dry

Opciones: ``--codigo ALT-01`` elige el repuesto a cotizar.

Este script valida el TRANSPORTE (SMTP + armado del correo). Para probar que el
agente decide llamar a la tool hace falta el entorno completo (requirements.txt)
y el caso de eval C16.
"""
from __future__ import annotations

import argparse
import json
import smtplib
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.email_sender import (  # noqa: E402
    ENVIO_LOG,
    enviar_cotizacion_documento,
    get_email_config,
    validar_email,
)
from tools.inventory_lookup import find_by_code, load_inventory, stock_status  # noqa: E402
from tools.pdf_cotizacion import generar_pdf  # noqa: E402


def mostrar_config(cfg: dict) -> None:
    print("Configuracion de correo")
    print(f"  modo          : {cfg['modo']} (pedido: {cfg['modo_pedido']})")
    print(f"  servidor      : {cfg['host']}:{cfg['puerto']}")
    print(f"  cifrado       : STARTTLS={cfg['tls']} SSL={cfg['ssl']}")
    print(f"  usuario       : {cfg['user'] or '(vacio)'}")
    print(f"  credenciales  : {'SI' if cfg['tiene_credenciales'] else 'NO'}")
    print(f"  domino perms. : {', '.join(cfg['dominios']) or '(sin restriccion)'}")
    print(f"  timeout       : {cfg['timeout']}s")


def probar_login(cfg: dict) -> bool:
    """Verifica las credenciales sin enviar ningun correo."""
    if not cfg["tiene_credenciales"]:
        print("\n[AVISO] Faltan SMTP_USER / SMTP_PASSWORD en .env.")
        print("        Ejecuta: .\\.venv\\Scripts\\python.exe scripts\\configurar_correo.py")
        return False

    print(f"\nProbando login en {cfg['host']}:{cfg['puerto']} (no se envia correo) ...")
    try:
        if cfg["ssl"]:
            servidor = smtplib.SMTP_SSL(cfg["host"], cfg["puerto"], timeout=cfg["timeout"])
        else:
            servidor = smtplib.SMTP(cfg["host"], cfg["puerto"], timeout=cfg["timeout"])
        try:
            servidor.ehlo()
            if cfg["tls"] and not cfg["ssl"]:
                servidor.starttls()
                servidor.ehlo()
            servidor.login(cfg["user"], cfg["password"])
        finally:
            try:
                servidor.quit()
            except Exception:
                pass
    except smtplib.SMTPAuthenticationError as exc:
        print(f"[ERROR] Credenciales rechazadas: {exc.smtp_code} {exc.smtp_error!r}")
        print("        Usa una contrasena de APLICACION de 16 caracteres y la cuenta completa.")
        return False
    except Exception as exc:
        print(f"[ERROR] {exc.__class__.__name__}: {exc}")
        print("        Si es timeout: SMTP_PORT=465, SMTP_SSL=1, SMTP_TLS=0.")
        return False

    print("[OK] Login correcto.")
    return True


def cotizacion_de_prueba(codigo: str) -> dict:
    """Arma un documento igual al que produce la tool, desde el inventario."""
    item = find_by_code(load_inventory(), codigo)
    if item is None:
        raise SystemExit(
            f"[ERROR] El codigo '{codigo}' no existe en el inventario. "
            "Prueba con ALT-01, FLT-01, ..."
        )
    return {
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "cliente": "Prueba SMTP",
        "vehiculo": "Suzuki Swift 2015",
        "items": [
            {
                "codigo": item["codigo"],
                "descripcion": item["descripcion"],
                "precio": int(item["precio"]),
                "stock": int(item["stock"]),
                "stock_status": stock_status(item),
            }
        ],
        "total": int(item["precio"]),
        "avisos": [],
    }


def adjunto_de_prueba(documento: dict) -> tuple[bytes, str]:
    """PDF de la cotizacion, igual al que adjunta la tool (D17)."""
    nombre = f"cotizacion_{datetime.now():%Y%m%d_%H%M%S}.pdf"
    return generar_pdf(documento, vehiculo=documento.get("vehiculo") or ""), nombre


def main() -> int:
    parser = argparse.ArgumentParser(description="Prueba el correo del agente.")
    parser.add_argument("--enviar", metavar="DESTINO", help="Envia de verdad a esa direccion.")
    parser.add_argument("--codigo", default="ALT-01", help="Codigo a cotizar (default ALT-01).")
    parser.add_argument("--dry", action="store_true", help="Fuerza modo dry-run.")
    args = parser.parse_args()

    if args.dry:
        # debe fijarse antes de leer la configuracion
        import os

        os.environ["EMAIL_MODE"] = "dry"

    cfg = get_email_config()
    mostrar_config(cfg)

    if args.dry:
        documento = cotizacion_de_prueba(args.codigo)
        adjunto, nombre_adjunto = adjunto_de_prueba(documento)
        resultado = enviar_cotizacion_documento(
            documento,
            "prueba@ejemplo.com",
            vehiculo=documento["vehiculo"],
            adjunto=adjunto,
            nombre_adjunto=nombre_adjunto,
        )
        print(f"\nResultado: {json.dumps(resultado, ensure_ascii=False, indent=2)}")
        print("\n[OK] Modo dry-run: revisa el .eml (con el PDF adjunto) en data/exports/.")
        return 0

    if not args.enviar:
        ok = probar_login(cfg)
        print("\nSiguiente paso: envia una cotizacion real a tu propia casilla")
        print(f"  .\\.venv\\Scripts\\python.exe scripts\\test_email.py --enviar {cfg['user'] or 'tu@correo.com'}")
        return 0 if ok else 1

    ok, motivo = validar_email(args.enviar)
    if not ok:
        print(f"[ERROR] {motivo}")
        return 1

    if cfg["modo"] != "smtp":
        print("\n[AVISO] El modo no es 'smtp': el correo NO saldra a internet.")
        print("        Revisa EMAIL_MODE y las credenciales en .env.")

    print(f"\nEnviando cotizacion de {args.codigo} a {args.enviar} ...")
    documento = cotizacion_de_prueba(args.codigo)
    adjunto, nombre_adjunto = adjunto_de_prueba(documento)
    resultado = enviar_cotizacion_documento(
        documento,
        args.enviar,
        vehiculo="Suzuki Swift 2015",
        mensaje="Prueba de envio del asistente de Repuestos Sur.",
        adjunto=adjunto,
        nombre_adjunto=nombre_adjunto,
    )
    print(json.dumps(resultado, ensure_ascii=False, indent=2))

    if resultado["enviado"]:
        print("\n[OK] El servidor SMTP acepto el mensaje. Revisa la bandeja del destinatario.")
        if ENVIO_LOG.exists():
            ultima = ENVIO_LOG.read_text(encoding="utf-8").strip().splitlines()[-1]
            print(f"Traza en {ENVIO_LOG}:\n  {ultima}")
        return 0

    print("\n[FALLO] El correo no se envio. Detalle arriba.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
