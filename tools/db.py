"""Base de datos interna de la tienda (SQLite de la biblioteca estandar).

Es la fuente operativa del stock y de las ventas:

    - ``repuestos``         : catalogo con el stock REAL (sincronizado con el CSV)
    - ``ventas``            : cabecera de cada venta (referencia V-0001, total, cliente)
    - ``venta_items``       : detalle de la venta (codigo, cantidad, precio)
    - ``movimientos_stock`` : auditoria de cada cambio de stock

Reglas de diseno:

    - La BD es la **verdad del stock**. El CSV ``data/internal/inventory.csv``
      conserva el catalogo (descripcion, marca, precio, compatibilidad) y se
      re-sincroniza con el stock real despues de cada venta, de modo que
      guardrails, tools, RAG y la interfaz web nunca muestren stock viejo.
    - Cero dependencias externas: solo ``sqlite3`` de la stdlib.
    - Una venta es atomica: o se descuenta todo, o no se toca el stock.
    - La ruta se puede aislar con ``TIENDA_DB_PATH`` (los evals usan una BD
      propia para no tocar la de operacion).
"""
from __future__ import annotations

import csv
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from tools.inventory_lookup import INVENTORY_PATH, ROOT

DEFAULT_DB_PATH = ROOT / "data" / "internal" / "tienda.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS repuestos (
    codigo                TEXT PRIMARY KEY,
    descripcion           TEXT NOT NULL DEFAULT '',
    marca                 TEXT NOT NULL DEFAULT '',
    categoria             TEXT NOT NULL DEFAULT '',
    vehiculos_compatibles TEXT NOT NULL DEFAULT '',
    precio                INTEGER NOT NULL DEFAULT 0,
    stock                 INTEGER NOT NULL DEFAULT 0,
    actualizado_en        TEXT
);

CREATE TABLE IF NOT EXISTS ventas (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    referencia TEXT UNIQUE,
    fecha     TEXT NOT NULL,
    cliente   TEXT,
    email     TEXT,
    vehiculo  TEXT,
    medio     TEXT,
    total     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS venta_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    venta_id        INTEGER NOT NULL REFERENCES ventas(id) ON DELETE CASCADE,
    codigo          TEXT NOT NULL,
    descripcion     TEXT,
    cantidad        INTEGER NOT NULL,
    precio_unitario INTEGER NOT NULL,
    subtotal        INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS movimientos_stock (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha             TEXT NOT NULL,
    codigo            TEXT NOT NULL,
    tipo              TEXT NOT NULL,
    delta             INTEGER NOT NULL,
    stock_resultante  INTEGER NOT NULL,
    nota              TEXT
);

CREATE INDEX IF NOT EXISTS idx_venta_items_venta ON venta_items(venta_id);
CREATE INDEX IF NOT EXISTS idx_movimientos_codigo ON movimientos_stock(codigo);
"""


class ErrorDB(Exception):
    """Error de negocio de la base de datos (no de infraestructura)."""


class RepuestoInexistente(ErrorDB):
    def __init__(self, codigo: str):
        super().__init__(f"el codigo '{codigo}' no existe en el inventario")
        self.codigo = codigo


class StockInsuficiente(ErrorDB):
    def __init__(self, codigo: str, disponible: int, pedido: int):
        super().__init__(
            f"stock insuficiente de {codigo}: hay {disponible} y se pidieron {pedido}"
        )
        self.codigo = codigo
        self.disponible = disponible
        self.pedido = pedido


class CantidadInvalida(ErrorDB):
    def __init__(self, codigo: str, cantidad: int):
        super().__init__(f"cantidad invalida para {codigo}: {cantidad}")
        self.codigo = codigo
        self.cantidad = cantidad


def db_path() -> Path:
    """Ruta del archivo SQLite (variable de entorno ``TIENDA_DB_PATH``).

    Las rutas relativas se resuelven contra la raiz del proyecto, para que la
    BD sea la misma sin importar desde donde se lance el proceso.
    """
    raw = (os.getenv("TIENDA_DB_PATH") or "").strip()
    if not raw:
        return DEFAULT_DB_PATH
    ruta = Path(raw)
    if not ruta.is_absolute():
        ruta = ROOT / ruta
    return ruta


@contextmanager
def conexion():
    """Conexion corta a la BD (una por operacion, segura con el server web)."""
    ruta = db_path()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(ruta), timeout=15, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=15000")
        conn.execute("PRAGMA foreign_keys=ON")
        yield conn
    finally:
        conn.close()


def _leer_csv_crudo() -> list[dict]:
    """Lee el CSV del inventario sin pasar por ``load_inventory``.

    Evita la recursion: ``load_inventory`` consulta el stock de la BD y la BD
    se siembra desde el CSV.
    """
    with open(INVENTORY_PATH, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def inicializar() -> Path:
    """Crea el esquema y siembra el catalogo desde el CSV si la BD esta vacia."""
    ruta = db_path()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with conexion() as conn:
        conn.executescript(SCHEMA)
        total = conn.execute("SELECT COUNT(*) AS n FROM repuestos").fetchone()["n"]
        if total == 0:
            ahora = datetime.now().isoformat(timespec="seconds")
            for fila in _leer_csv_crudo():
                conn.execute(
                    "INSERT OR IGNORE INTO repuestos "
                    "(codigo, descripcion, marca, categoria, vehiculos_compatibles, "
                    " precio, stock, actualizado_en) VALUES (?,?,?,?,?,?,?,?)",
                    (
                        fila["codigo"],
                        fila.get("descripcion", ""),
                        fila.get("marca", ""),
                        fila.get("categoria", ""),
                        fila.get("vehiculos_compatibles", ""),
                        int(fila.get("precio") or 0),
                        int(fila.get("stock") or 0),
                        ahora,
                    ),
                )
    return ruta


def catalogo() -> list[dict]:
    """Filas de ``repuestos`` (con el stock real) como diccionarios."""
    inicializar()
    with conexion() as conn:
        filas = conn.execute(
            "SELECT codigo, descripcion, marca, categoria, vehiculos_compatibles, "
            "precio, stock FROM repuestos ORDER BY codigo"
        ).fetchall()
    return [dict(f) for f in filas]


def stock_por_codigo() -> dict[str, int]:
    """Mapa codigo -> stock real (semilla la BD la primera vez)."""
    inicializar()
    with conexion() as conn:
        filas = conn.execute("SELECT codigo, stock FROM repuestos").fetchall()
    return {f["codigo"]: int(f["stock"]) for f in filas}


def stock_de(codigo: str) -> int | None:
    """Stock real de un codigo, o None si el codigo no existe."""
    inicializar()
    with conexion() as conn:
        fila = conn.execute(
            "SELECT stock FROM repuestos WHERE codigo = ?", (codigo,)
        ).fetchone()
    return int(fila["stock"]) if fila else None


def registrar_venta(
    items: list[dict],
    cliente: str = "",
    email: str = "",
    vehiculo: str = "",
    medio: str = "chat",
) -> dict:
    """Registra una venta y descuenta el stock en una sola transaccion.

    ``items`` es una lista de dicts con ``codigo``, ``cantidad`` y
    ``precio_unitario`` (el precio lo pone el llamador, que lo lee del
    inventario). Si algun codigo no existe o no hay stock suficiente, no se
    descuenta nada: la operacion se revierte completa.

    Devuelve el detalle de la venta: referencia, total, items y el stock
    antes/despues de cada codigo.
    """
    inicializar()
    ahora = datetime.now().isoformat(timespec="seconds")
    detalle: list[dict] = []

    with conexion() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            for item in items:
                codigo = str(item["codigo"])
                cantidad = int(item.get("cantidad") or 0)
                if cantidad <= 0:
                    raise CantidadInvalida(codigo, cantidad)
                fila = conn.execute(
                    "SELECT codigo, descripcion, precio, stock FROM repuestos "
                    "WHERE codigo = ?",
                    (codigo,),
                ).fetchone()
                if fila is None:
                    raise RepuestoInexistente(codigo)
                if int(fila["stock"]) < cantidad:
                    raise StockInsuficiente(codigo, int(fila["stock"]), cantidad)
                precio = int(item.get("precio_unitario") or fila["precio"])
                detalle.append(
                    {
                        "codigo": codigo,
                        "descripcion": fila["descripcion"],
                        "cantidad": cantidad,
                        "precio_unitario": precio,
                        "subtotal": precio * cantidad,
                        "stock_antes": int(fila["stock"]),
                    }
                )

            total = sum(d["subtotal"] for d in detalle)
            cur = conn.execute(
                "INSERT INTO ventas (referencia, fecha, cliente, email, vehiculo, "
                "medio, total) VALUES (?,?,?,?,?,?,?)",
                (
                    None,
                    ahora,
                    cliente or "",
                    email or "",
                    vehiculo or "",
                    medio or "",
                    total,
                ),
            )
            venta_id = int(cur.lastrowid)
            referencia = f"V-{venta_id:04d}"
            conn.execute(
                "UPDATE ventas SET referencia = ? WHERE id = ?", (referencia, venta_id)
            )

            for d in detalle:
                conn.execute(
                    "INSERT INTO venta_items (venta_id, codigo, descripcion, cantidad, "
                    "precio_unitario, subtotal) VALUES (?,?,?,?,?,?)",
                    (
                        venta_id,
                        d["codigo"],
                        d["descripcion"],
                        d["cantidad"],
                        d["precio_unitario"],
                        d["subtotal"],
                    ),
                )
                nuevo_stock = d["stock_antes"] - d["cantidad"]
                conn.execute(
                    "UPDATE repuestos SET stock = ?, actualizado_en = ? WHERE codigo = ?",
                    (nuevo_stock, ahora, d["codigo"]),
                )
                conn.execute(
                    "INSERT INTO movimientos_stock (fecha, codigo, tipo, delta, "
                    "stock_resultante, nota) VALUES (?,?,?,?,?,?)",
                    (
                        ahora,
                        d["codigo"],
                        "venta",
                        -d["cantidad"],
                        nuevo_stock,
                        f"venta {referencia}",
                    ),
                )
                d["stock_despues"] = nuevo_stock

            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    return {
        "venta_id": venta_id,
        "referencia": referencia,
        "fecha": ahora,
        "cliente": cliente or "",
        "email": email or "",
        "vehiculo": vehiculo or "",
        "medio": medio or "",
        "total": total,
        "items": detalle,
    }


def ajustar_stock(codigo: str, delta: int, tipo: str = "reabastecimiento", nota: str = "") -> int:
    """Suma (delta > 0) o resta stock de un codigo. Devuelve el stock final.

    Se usa para reponer mercaderia y paraRestablecer el inventario en las
    pruebas; las ventas de verdad van por ``registrar_venta``.
    """
    inicializar()
    ahora = datetime.now().isoformat(timespec="seconds")
    with conexion() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            fila = conn.execute(
                "SELECT stock FROM repuestos WHERE codigo = ?", (codigo,)
            ).fetchone()
            if fila is None:
                raise RepuestoInexistente(codigo)
            nuevo = int(fila["stock"]) + int(delta)
            if nuevo < 0:
                raise StockInsuficiente(codigo, int(fila["stock"]), abs(int(delta)))
            conn.execute(
                "UPDATE repuestos SET stock = ?, actualizado_en = ? WHERE codigo = ?",
                (nuevo, ahora, codigo),
            )
            conn.execute(
                "INSERT INTO movimientos_stock (fecha, codigo, tipo, delta, "
                "stock_resultante, nota) VALUES (?,?,?,?,?,?)",
                (ahora, codigo, tipo, int(delta), nuevo, nota),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return nuevo


def ventas_recientes(limite: int = 10) -> list[dict]:
    """Ultimas ventas registradas (mas recientes primero)."""
    inicializar()
    with conexion() as conn:
        filas = conn.execute(
            "SELECT id, referencia, fecha, cliente, email, vehiculo, medio, total "
            "FROM ventas ORDER BY id DESC LIMIT ?",
            (int(limite),),
        ).fetchall()
    return [dict(f) for f in filas]


def items_de_venta(venta_id: int) -> list[dict]:
    """Detalle (items) de una venta por su id."""
    inicializar()
    with conexion() as conn:
        filas = conn.execute(
            "SELECT codigo, descripcion, cantidad, precio_unitario, subtotal "
            "FROM venta_items WHERE venta_id = ? ORDER BY id",
            (int(venta_id),),
        ).fetchall()
    return [dict(f) for f in filas]


def movimientos(codigo: str = "", limite: int = 50) -> list[dict]:
    """Auditoria de movimientos de stock (de un codigo o de todos)."""
    inicializar()
    with conexion() as conn:
        if codigo:
            filas = conn.execute(
                "SELECT fecha, codigo, tipo, delta, stock_resultante, nota "
                "FROM movimientos_stock WHERE codigo = ? ORDER BY id DESC LIMIT ?",
                (codigo, int(limite)),
            ).fetchall()
        else:
            filas = conn.execute(
                "SELECT fecha, codigo, tipo, delta, stock_resultante, nota "
                "FROM movimientos_stock ORDER BY id DESC LIMIT ?",
                (int(limite),),
            ).fetchall()
    return [dict(f) for f in filas]


def resumen() -> dict:
    """Resumen operativo para la interfaz y las verificaciones."""
    inicializar()
    with conexion() as conn:
        repuestos = conn.execute("SELECT COUNT(*) AS n FROM repuestos").fetchone()["n"]
        ventas = conn.execute("SELECT COUNT(*) AS n FROM ventas").fetchone()["n"]
        facturado = conn.execute(
            "SELECT COALESCE(SUM(total), 0) AS t FROM ventas"
        ).fetchone()["t"]
        bajo = conn.execute(
            "SELECT COUNT(*) AS n FROM repuestos WHERE stock > 0 AND stock < 5"
        ).fetchone()["n"]
        agotados = conn.execute(
            "SELECT COUNT(*) AS n FROM repuestos WHERE stock <= 0"
        ).fetchone()["n"]
    return {
        "db": str(db_path()),
        "repuestos": int(repuestos),
        "ventas": int(ventas),
        "facturado": int(facturado),
        "stock_bajo": int(bajo),
        "agotados": int(agotados),
    }
