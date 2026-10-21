"""Envio de cotizaciones por correo electronico (SMTP con la stdlib).

Modulo hermano de ``tools/inventory_lookup.py``: sin dependencias externas
(solo ``smtplib``/``email`` de la biblioteca estandar) y con una regla clara:
el modulo **no decide** si la cotizacion es valida ni inventa precios, solo
transporta un documento ya construido desde el CSV.

Modo de operacion (variable ``EMAIL_MODE``):

    - ``smtp`` : envia de verdad por SMTP. Requiere ``SMTP_USER`` y
      ``SMTP_PASSWORD``.
    - ``dry``  : no sale nada a internet. El correo se guarda como ``.eml`` en
      ``data/exports/`` para revision manual.
    - ``auto`` (default): usa ``smtp`` si hay credenciales, ``dry`` si no.

El modo por defecto es ``dry``, de modo que un prototipo, una corrida de evals
o una prueba nunca envia un correo real por accidente. Ademas, cada envio
(preparado o realizado) queda registrado en ``data/exports/envios.jsonl`` para
trazabilidad, igual que la traza del agente.
"""
from __future__ import annotations

import json
import os
import re
import smtplib
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr, parseaddr
from pathlib import Path

from dotenv import load_dotenv

from tools.inventory_lookup import ROOT

load_dotenv()

EXPORT_DIR = ROOT / "data" / "exports"
ENVIO_LOG = EXPORT_DIR / "envios.jsonl"

# Validacion basica de direccion (suficiente para el prototipo y para el LLM).
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

# Etiqueta visible de cada estado de stock en el correo.
ETIQUETA_STOCK = {
    "ok": "",
    "critico": " (STOCK BAJO)",
    "agotado": " (AGOTADO)",
}


# --------------------------------------------------------------------------
# Configuracion
# --------------------------------------------------------------------------
def get_email_config() -> dict:
    """Configuracion de correo. Siempre devuelve un dict (nunca None).

    ``modo`` queda resuelto a ``smtp`` o ``dry``: si se pide ``smtp`` pero no
    hay credenciales, cae a ``dry`` en vez de fallar en caliente.
    """
    modo_pedido = (os.getenv("EMAIL_MODE") or "auto").strip().lower()
    if modo_pedido not in ("smtp", "dry", "auto"):
        modo_pedido = "auto"

    user = (os.getenv("SMTP_USER") or "").strip()
    password = os.getenv("SMTP_PASSWORD") or ""
    tiene_credenciales = bool(user and password)

    if modo_pedido == "auto":
        modo = "smtp" if tiene_credenciales else "dry"
    elif modo_pedido == "smtp":
        modo = "smtp" if tiene_credenciales else "dry"
    else:
        modo = "dry"

    dominios = [
        d.strip().lower().lstrip("@")
        for d in (os.getenv("EMAIL_DOMAINS_ALLOWLIST") or "").split(",")
        if d.strip()
    ]

    try:
        puerto = int(os.getenv("SMTP_PORT") or 587)
    except ValueError:
        puerto = 587

    try:
        timeout = float(os.getenv("EMAIL_TIMEOUT_S") or 15)
    except ValueError:
        timeout = 15.0

    return {
        "modo": modo,
        "modo_pedido": modo_pedido,
        "tiene_credenciales": tiene_credenciales,
        "host": (os.getenv("SMTP_HOST") or "smtp.gmail.com").strip(),
        "puerto": puerto,
        "user": user,
        "password": password,
        "tls": (os.getenv("SMTP_TLS") or "1").strip().lower() not in ("0", "false", "no"),
        "ssl": (os.getenv("SMTP_SSL") or "0").strip().lower() in ("1", "true", "yes"),
        "remitente": (os.getenv("EMAIL_FROM") or "").strip(),
        "timeout": timeout,
        "dominios": dominios,
    }


def correo_configurado() -> bool:
    """True si el envio real por SMTP esta disponible."""
    return get_email_config()["modo"] == "smtp"


# --------------------------------------------------------------------------
# Validacion
# --------------------------------------------------------------------------
def validar_email(direccion: str) -> tuple[bool, str]:
    """Valida la forma de una direccion. Devuelve (ok, motivo_del_error)."""
    direccion = (direccion or "").strip()
    if not direccion:
        return False, "no se indico ninguna direccion de correo"
    if len(direccion) > 254 or ".." in direccion or direccion.startswith("@"):
        return False, f"'{direccion}' no es una direccion de correo valida"
    if not EMAIL_RE.match(direccion):
        return False, f"'{direccion}' no es una direccion de correo valida"
    return True, ""


def dominio_permitido(direccion: str, dominios: list[str]) -> bool:
    """True si el dominio del destinatario esta en la lista blanca.

    Lista vacia = sin restriccion (la tienda opera sin politica de dominio).
    """
    if not dominios:
        return True
    _, addr = parseaddr(direccion or "")
    dominio = (addr.split("@")[-1] if "@" in addr else "").lower()
    return dominio in dominios


# --------------------------------------------------------------------------
# Cuerpo del correo
# --------------------------------------------------------------------------
def formatear_precio(valor) -> str:
    """Formatea un precio como entero con separador de miles (estilo CLP)."""
    try:
        return f"{int(valor):,}".replace(",", ".")
    except (TypeError, ValueError):
        return str(valor)


_precio = formatear_precio


def _linea_item(item: dict) -> str:
    etiqueta = ETIQUETA_STOCK.get(item.get("stock_status", "ok"), "")
    return (
        f"- [{item['codigo']}] {item['descripcion']} - ${_precio(item['precio'])} - "
        f"Stock: {item['stock']}{etiqueta}"
    )


def construir_cuerpo_texto(documento: dict, vehiculo: str = "", mensaje: str = "") -> str:
    """Cuerpo en texto plano de la cotizacion (visible sin HTML)."""
    cliente = documento.get("cliente") or "no indicado"
    lineas = [
        "COTIZACION - REPUESTOS SUR",
        "",
        f"Fecha: {documento.get('fecha', '')}",
        f"Cliente: {cliente}",
    ]
    if vehiculo:
        lineas.append(f"Vehiculo: {vehiculo}")
    lineas += ["", "Detalle:"]
    lineas += [_linea_item(i) for i in documento.get("items", [])]
    lineas += ["", f"TOTAL: ${_precio(documento.get('total', 0))}"]

    avisos = documento.get("avisos") or []
    if avisos:
        lineas += ["", "Avisos: " + "; ".join(avisos)]

    if mensaje:
        lineas += ["", mensaje.strip()]

    lineas += [
        "",
        "--",
        "Repuestos Sur | Asistente de ventas",
        "Esta cotizacion se genero automaticamente con precios y stock tomados "
        "del inventario de la tienda.",
    ]
    return "\n".join(lineas)


def construir_cuerpo_html(documento: dict, vehiculo: str = "", mensaje: str = "") -> str:
    """Cuerpo HTML de la cotizacion (alternativa al texto plano)."""
    cliente = documento.get("cliente") or "no indicado"
    filas = []
    for item in documento.get("items", []):
        etiqueta = ETIQUETA_STOCK.get(item.get("stock_status", "ok"), "")
        aviso = (
            f"<br><span style='color:#b3261e;font-weight:bold'>"
            f"{'STOCK BAJO' if item.get('stock_status') == 'critico' else 'AGOTADO'}"
            f"</span>"
            if etiqueta
            else ""
        )
        filas.append(
            "<tr>"
            f"<td><b>[{item['codigo']}]</b> {item['descripcion']}{aviso}</td>"
            f"<td align='right'>${_precio(item['precio'])}</td>"
            f"<td align='right'>{item['stock']}</td>"
            "</tr>"
        )

    avisos = documento.get("avisos") or []
    bloque_avisos = (
        "<p style='color:#b3261e'><b>Avisos:</b> " + "; ".join(avisos) + "</p>"
        if avisos
        else ""
    )
    bloque_mensaje = f"<p>{mensaje.strip()}</p>" if mensaje else ""
    bloque_vehiculo = f"<p><b>Vehiculo:</b> {vehiculo}</p>" if vehiculo else ""

    return f"""<html>
<body style="font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#222">
  <h2 style="margin:0 0 4px">Cotización - Repuestos Sur</h2>
  <p style="margin:0 0 12px;color:#666">
    Fecha: {documento.get('fecha', '')}<br>
    Cliente: {cliente}
  </p>
  {bloque_vehiculo}
  <table cellpadding="6" cellspacing="0" border="1" style="border-collapse:collapse;width:100%">
    <thead style="background:#f2f2f2">
      <tr><th align='left'>Repuesto</th><th align='right'>Precio</th><th align='right'>Stock</th></tr>
    </thead>
    <tbody>
      {''.join(filas)}
    </tbody>
    <tfoot>
      <tr style="background:#f2f2f2">
        <td><b>TOTAL</b></td>
        <td align='right'><b>${_precio(documento.get('total', 0))}</b></td>
        <td></td>
      </tr>
    </tfoot>
  </table>
  {bloque_avisos}
  {bloque_mensaje}
  <hr style="border:none;border-top:1px solid #ddd">
  <p style="font-size:12px;color:#666">
    Repuestos Sur | Asistente de ventas<br>
    Cotización generada automáticamente con precios y stock del inventario de la tienda.
  </p>
</body>
</html>"""


def _remitente(cfg: dict) -> tuple[str, str]:
    """Devuelve (direccion, nombre visible) del remitente."""
    bruto = cfg.get("remitente") or ""
    if not bruto:
        return cfg.get("user") or "cotizaciones@localhost", "Repuestos Sur"
    nombre, addr = parseaddr(bruto)
    if not addr:
        addr = cfg.get("user") or "cotizaciones@localhost"
    return addr, nombre or "Repuestos Sur"


def _asunto(documento: dict, vehiculo: str = "") -> str:
    cliente = documento.get("cliente") or "no indicado"
    if vehiculo:
        return f"Cotización de repuestos - {vehiculo} - {cliente}"
    return f"Cotización de repuestos - {cliente}"


def _armar_mensaje(
    documento: dict,
    destinatario: str,
    cfg: dict,
    vehiculo: str = "",
    mensaje: str = "",
    adjunto: bytes | None = None,
    nombre_adjunto: str = "",
) -> EmailMessage:
    """Construye el EmailMessage con texto plano, HTML y adjunto opcional."""
    addr, nombre = _remitente(cfg)
    msg = EmailMessage()
    msg["Subject"] = _asunto(documento, vehiculo)
    msg["From"] = formataddr((nombre, addr))
    msg["To"] = destinatario
    msg["Reply-To"] = addr
    msg.set_content(construir_cuerpo_texto(documento, vehiculo, mensaje))
    msg.add_alternative(construir_cuerpo_html(documento, vehiculo, mensaje), subtype="html")
    if adjunto and nombre_adjunto:
        msg.add_attachment(
            adjunto, maintype="application", subtype="json", filename=nombre_adjunto
        )
    return msg


# --------------------------------------------------------------------------
# Envio
# --------------------------------------------------------------------------
def _smtp_send(msg: EmailMessage, cfg: dict) -> None:
    """Envia el mensaje por SMTP. Lanza excepcion si falla."""
    host, puerto, timeout = cfg["host"], cfg["puerto"], cfg["timeout"]
    if cfg["ssl"]:
        server = smtplib.SMTP_SSL(host, puerto, timeout=timeout)
    else:
        server = smtplib.SMTP(host, puerto, timeout=timeout)
    try:
        server.ehlo()
        if cfg["tls"] and not cfg["ssl"]:
            server.starttls()
            server.ehlo()
        if cfg["user"]:
            server.login(cfg["user"], cfg["password"])
        server.send_message(msg)
    finally:
        try:
            server.quit()
        except Exception:
            pass


def enviar_cotizacion_documento(
    documento: dict,
    destinatario: str,
    vehiculo: str = "",
    mensaje: str = "",
    adjunto: bytes | None = None,
    nombre_adjunto: str = "",
) -> dict:
    """Prepara y, si corresponde, envia el correo de la cotizacion.

    Devuelve el veredicto **real** (nunca una suposicion):

        {"modo", "enviado", "ruta", "detalle"}

    ``enviado`` es True solo si el servidor SMTP acepto el mensaje.
    """
    cfg = get_email_config()
    resultado = {
        "modo": cfg["modo"],
        "enviado": False,
        "ruta": None,
        "detalle": "",
    }

    ok, motivo = validar_email(destinatario)
    if not ok:
        resultado["detalle"] = f"Direccion invalida: {motivo}."
        return resultado

    if not dominio_permitido(destinatario, cfg["dominios"]):
        resultado["detalle"] = (
            "El dominio del destinatario no esta en la lista permitida "
            f"({', '.join(cfg['dominios'])})."
        )
        return resultado

    destinatario = destinatario.strip()
    try:
        msg = _armar_mensaje(
            documento, destinatario, cfg, vehiculo, mensaje, adjunto, nombre_adjunto
        )
    except Exception as exc:
        resultado["detalle"] = f"No pude armar el correo ({exc.__class__.__name__}: {exc})."
        return resultado

    if cfg["modo"] == "smtp":
        try:
            _smtp_send(msg, cfg)
        except Exception as exc:
            resultado["detalle"] = (
                f"Fallo el envio SMTP ({exc.__class__.__name__}: {exc})."
            )
            _registrar_envio(documento, destinatario, cfg, resultado, vehiculo)
            return resultado
        resultado["enviado"] = True
        resultado["detalle"] = f"Correo enviado a {destinatario}."
    else:
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ruta = EXPORT_DIR / f"cotizacion_{stamp}.eml"
        ruta.write_bytes(msg.as_bytes())
        resultado["ruta"] = str(ruta)
        resultado["detalle"] = (
            f"Cotizacion preparada en {ruta} (modo dry-run, NO se envio)."
        )

    _registrar_envio(documento, destinatario, cfg, resultado, vehiculo)
    return resultado


# --------------------------------------------------------------------------
# Trazabilidad
# --------------------------------------------------------------------------
def _registrar_envio(
    documento: dict,
    destinatario: str,
    cfg: dict,
    resultado: dict,
    vehiculo: str = "",
) -> None:
    """Deja una linea en data/exports/envios.jsonl con el resultado real."""
    registro = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "destinatario": destinatario,
        "cliente": documento.get("cliente"),
        "vehiculo": vehiculo or documento.get("vehiculo") or "",
        "modo": cfg["modo"],
        "enviado": resultado["enviado"],
        "detalle": resultado["detalle"],
        "ruta": resultado["ruta"],
        "total": documento.get("total", 0),
        "items": [
            {"codigo": i["codigo"], "precio": i["precio"], "stock": i["stock"]}
            for i in documento.get("items", [])
        ],
    }
    try:
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        with open(ENVIO_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(registro, ensure_ascii=False) + "\n")
    except Exception:
        # La trazabilidad nunca debe tumbar el flujo del agente.
        pass
