"""Pruebas de las herramientas de venta, recomendacion y correo.

No gastan tokens del LLM: verifican las tools directamente sobre una copia
del inventario y una base de datos temporal.

Uso (desde la raiz del proyecto, con el entorno virtual activo):
    .venv\\Scripts\\python -m pytest tests/test_herramientas.py -v
"""
from __future__ import annotations

import os
import shutil
import socket
import socketserver
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="repuestos_test_"))
CSV_TEST = TMP / "inventory.csv"
shutil.copyfile(ROOT / "data" / "internal" / "inventory.csv", CSV_TEST)

os.environ["INVENTORY_PATH"] = str(CSV_TEST)
os.environ["TIENDA_DB_PATH"] = str(TMP / "tienda_test.db")
os.environ["EMAIL_MODE"] = "dry"

from agent import tools as agent_tools  # noqa: E402
from tools import db  # noqa: E402
from tools import email_sender  # noqa: E402
from tools import inventory_lookup as inv  # noqa: E402


def _limpiar_estado():
    """Deja la BD de prueba como recien sembrada y recarga el cache."""
    for sufijo in ("", "-wal", "-shm"):
        ruta = Path(str(TMP / "tienda_test.db") + sufijo)
        if ruta.exists():
            ruta.unlink()
    db.inicializar()
    shutil.copyfile(ROOT / "data" / "internal" / "inventory.csv", CSV_TEST)
    agent_tools.reload_inventory()


# --------------------------------------------------------------------------
# Base de datos interna
# --------------------------------------------------------------------------
def test_la_bd_se_siembra_desde_el_csv():
    _limpiar_estado()
    filas = db.catalogo()
    assert len(filas) == 12
    assert {f["codigo"] for f in filas} >= {"ALT-01", "FLT-02"}


def test_el_inventario_trae_el_stock_real_de_la_bd():
    _limpiar_estado()
    db.ajustar_stock("ALT-01", -2, tipo="ajuste", nota="prueba")
    filas = inv.load_inventory()
    alt01 = next(f for f in filas if f["codigo"] == "ALT-01")
    assert alt01["stock"] == "5"


def test_una_venta_descuenta_el_stock():
    _limpiar_estado()
    antes = db.stock_de("ALT-01")
    venta = db.registrar_venta(
        [{"codigo": "ALT-01", "cantidad": 2, "precio_unitario": 289990}],
        cliente="Juan Perez",
    )
    assert venta["referencia"].startswith("V-")
    assert venta["total"] == 2 * 289990
    assert db.stock_de("ALT-01") == antes - 2
    assert db.ventas_recientes()[0]["cliente"] == "Juan Perez"


def test_una_venta_sin_stock_no_modifica_nada():
    _limpiar_estado()
    antes = db.stock_de("ALT-02")
    try:
        db.registrar_venta([{"codigo": "ALT-02", "cantidad": 999, "precio_unitario": 1}])
        raise AssertionError("deberia haber fallado por falta de stock")
    except db.StockInsuficiente:
        pass
    assert db.stock_de("ALT-02") == antes
    assert db.ventas_recientes() == []


def test_el_csv_se_sincroniza_con_el_stock_real():
    _limpiar_estado()
    db.registrar_venta([{"codigo": "ALT-01", "cantidad": 1, "precio_unitario": 289990}])
    inv.sincronizar_stock_csv(db.stock_por_codigo(), path=CSV_TEST)
    filas = inv.load_inventory()
    alt01 = next(f for f in filas if f["codigo"] == "ALT-01")
    alt02 = next(f for f in filas if f["codigo"] == "ALT-02")
    assert alt01["stock"] == "6"
    assert alt02["stock"] == "4"


# --------------------------------------------------------------------------
# Tool registrar_venta
# --------------------------------------------------------------------------
def test_registrar_venta_devuelve_referencia_y_stock_antes_despues():
    _limpiar_estado()
    salida = agent_tools.registrar_venta.invoke(
        {"codigos": ["ALT-02"], "cliente": "Ana"}
    )
    assert "REGISTRADA" in salida
    assert "V-" in salida
    assert "stock 4 -> 3" in salida
    assert db.stock_de("ALT-02") == 3


def test_registrar_venta_rechaza_un_codigo_inexistente():
    _limpiar_estado()
    salida = agent_tools.registrar_venta.invoke({"codigos": ["XYZ-99"]})
    assert "No registre la venta" in salida
    assert db.ventas_recientes() == []


def test_registrar_venta_rechaza_falta_de_stock():
    _limpiar_estado()
    salida = agent_tools.registrar_venta.invoke(
        {"codigos": ["ALT-02"], "cantidades": [99]}
    )
    assert "falta de stock" in salida.lower()
    assert db.stock_de("ALT-02") == 4


# --------------------------------------------------------------------------
# Tool recomendar_repuesto
# --------------------------------------------------------------------------
def test_recomendar_repuesto_devuelve_el_codigo_y_la_compatibilidad():
    _limpiar_estado()
    salida = agent_tools.recomendar_repuesto.invoke(
        {"marca": "Suzuki", "modelo": "Swift", "anio": "2015"}
    )
    assert "ALT-01" in salida
    assert "RECOMENDACION" in salida
    assert "compatible" in salida.lower()


def test_recomendar_repuesto_pide_los_datos_del_vehiculo():
    _limpiar_estado()
    salida = agent_tools.recomendar_repuesto.invoke(
        {"marca": "Suzuki", "modelo": "", "anio": ""}
    )
    assert "marca, modelo y anio" in salida


def test_recomendar_repuesto_no_improvisa_para_un_vehiculo_desconocido():
    _limpiar_estado()
    salida = agent_tools.recomendar_repuesto.invoke(
        {"marca": "Ferrari", "modelo": "488", "anio": "2020"}
    )
    assert "Ferrari" in salida
    assert "no tengo informacion suficiente" in salida.lower()


# --------------------------------------------------------------------------
# Correo: dry-run y envio real por SMTP
# --------------------------------------------------------------------------
class _SMTPHandler(socketserver.StreamRequestHandler):
    """Servidor SMTP minimo para probar el camino de envio real."""

    def handle(self):
        w = self.wfile
        w.write(b"220 localhost ESMTP prueba\r\n")
        while True:
            linea = self.rfile.readline()
            if not linea:
                break
            cmd = linea.decode("utf-8", "replace").strip()
            mayus = cmd.upper()
            if mayus.startswith("EHLO"):
                w.write(b"250-localhost\r\n250-AUTH LOGIN\r\n250 OK\r\n")
            elif mayus.startswith("HELO"):
                w.write(b"250 localhost\r\n")
            elif mayus.startswith("AUTH LOGIN"):
                w.write(b"334 VXNlcm5hbWU6\r\n")
                self.rfile.readline()
                w.write(b"334 UGFzc3dvcmQ6\r\n")
                self.rfile.readline()
                w.write(b"235 Authentication successful\r\n")
            elif mayus.startswith("AUTH"):
                w.write(b"235 Authentication successful\r\n")
            elif mayus.startswith("DATA"):
                w.write(b"354 End data with <CR><LF>.<CR><LF>\r\n")
                while True:
                    data = self.rfile.readline()
                    if not data or data.strip() == b".":
                        break
                w.write(b"250 OK: message accepted\r\n")
            elif mayus.startswith("QUIT"):
                w.write(b"221 Bye\r\n")
                break
            else:
                w.write(b"250 OK\r\n")


class _ServidorSMTP:
    """Levanta el servidor SMTP de prueba en un hilo."""

    def __init__(self):
        self._server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _SMTPHandler)
        self._server.daemon_threads = True
        self.puerto = self._server.server_address[1]
        self._hilo = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self):
        self._hilo.start()
        return self

    def __exit__(self, *exc):
        self._server.shutdown()
        self._server.server_close()


def _documento_venta():
    return {
        "tipo": "comprobante",
        "referencia": "V-0001",
        "fecha": "2026-10-22T10:00:00",
        "cliente": "Ana",
        "vehiculo": "Suzuki Swift 2015",
        "items": [
            {
                "codigo": "ALT-01",
                "descripcion": "Alternador 12V 90A",
                "precio": 289990,
                "stock": 6,
                "stock_status": "ok",
                "cantidad": 1,
            }
        ],
        "total": 289990,
        "avisos": [],
    }


def test_el_modo_dry_no_sale_a_internet(monkeypatch):
    monkeypatch.setenv("EMAIL_MODE", "dry")
    resultado = email_sender.enviar_cotizacion_documento(
        _documento_venta(), "cliente@ejemplo.com"
    )
    assert resultado["enviado"] is False
    assert resultado["ruta"] and Path(resultado["ruta"]).exists()


def test_el_modo_smtp_manda_el_correo_de_verdad(monkeypatch):
    with _ServidorSMTP() as servidor:
        monkeypatch.setenv("EMAIL_MODE", "smtp")
        monkeypatch.setenv("SMTP_HOST", "127.0.0.1")
        monkeypatch.setenv("SMTP_PORT", str(servidor.puerto))
        monkeypatch.setenv("SMTP_TLS", "0")
        monkeypatch.setenv("SMTP_SSL", "0")
        monkeypatch.setenv("SMTP_USER", "vendedor@ejemplo.com")
        monkeypatch.setenv("SMTP_PASSWORD", "secreto")
        monkeypatch.setenv("EMAIL_DOMAINS_ALLOWLIST", "ejemplo.com")
        resultado = email_sender.enviar_cotizacion_documento(
            _documento_venta(), "cliente@ejemplo.com"
        )
    assert resultado["enviado"] is True
    assert resultado["modo"] == "smtp"


def test_el_comprobante_de_venta_dice_comprobante():
    asunto = email_sender._asunto(_documento_venta())
    cuerpo = email_sender.construir_cuerpo_texto(_documento_venta())
    assert "Comprobante" in asunto
    assert "COMPROBANTE DE VENTA V-0001" in cuerpo


def test_un_dominio_fuera_de_la_lista_blanca_no_se_envia(monkeypatch):
    monkeypatch.setenv("EMAIL_MODE", "smtp")
    monkeypatch.setenv("SMTP_USER", "vendedor@ejemplo.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secreto")
    monkeypatch.setenv("EMAIL_DOMAINS_ALLOWLIST", "gmail.com")
    resultado = email_sender.enviar_cotizacion_documento(
        _documento_venta(), "cliente@otrodominio.com"
    )
    assert resultado["enviado"] is False
    assert "lista permitida" in resultado["detalle"]


def test_una_direccion_invalida_no_se_envia():
    ok, motivo = email_sender.validar_email("no-es-un-correo")
    assert ok is False
    assert "valida" in motivo
