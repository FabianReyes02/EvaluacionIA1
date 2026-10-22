"""Generador de PDF para cotizaciones y comprobantes (solo biblioteca estandar).

Escribe un PDF 1.4 con las fuentes base-14 (Helvetica y Helvetica-Bold) en
codificacion WinAnsi, suficiente para el espanol (tildes, enie y signos de
puntuacion). No usa librerias externas a proposito: el documento es una tabla
de texto simple, el entorno de desarrollo ya bloqueo extensiones binarias
(D11) y la decision D17 prefiere no sumar dependencias.

El modulo **no decide** nada sobre la cotizacion: recibe el mismo documento
que arma ``agent/tools.py`` desde el CSV (precios y stock reales) y lo dibuja.

Uso:
    from tools.pdf_cotizacion import generar_pdf, guardar_pdf

    pdf = generar_pdf(documento, vehiculo="Suzuki Swift 2015")
    guardar_pdf(documento, Path("data/exports/cotizacion.pdf"))
"""
from __future__ import annotations

from pathlib import Path

ANCHO, ALTO = 595.28, 841.89  # A4 en puntos
MARGEN = 50.0
DERECHA = ANCHO - MARGEN

# Caracteres que WinAnsi no cubre (o que se ven mejor como ASCII) y que el
# modelo suele colar en las descripciones: se normalizan antes de codificar.
_NORMALIZAR = str.maketrans(
    {
        "\u2014": "-",  # em dash
        "\u2013": "-",  # en dash
        "\u2212": "-",  # signo menos
        "\u00d7": "x",  # multiplicacion
        "\u201c": '"',
        "\u201d": '"',
        "\u2018": "'",
        "\u2019": "'",
        "\u2022": "-",  # vineta
        "\u2026": "...",
        "\u2192": "->",
        "\u2190": "<-",
        "\u00a0": " ",
        "\t": " ",
        "\n": " ",
    }
)

# Tinta (RGB 0-1) usada en el documento.
NEGRO = (0.12, 0.12, 0.12)
GRIS = (0.55, 0.55, 0.55)
GRIS_FONDO = (0.93, 0.93, 0.93)
GRIS_LINEA = (0.82, 0.82, 0.82)
ROJO = (0.70, 0.13, 0.10)

# Anchos de Helvetica y Helvetica-Bold para ASCII 32..126, en miles de
# unidad de em (tablas AFM de las fuentes base-14). Alcanza para alinear a
# la derecha y recortar descripciones; el resto de los glifos usa un ancho
# promedio.
_ANCHOS_HELVETICA = [
    278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,
    1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,
    333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
    556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584,
]
_ANCHOS_BOLD = [
    278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 333, 333, 584, 584, 584, 611,
    975, 722, 722, 722, 722, 667, 611, 778, 722, 278, 556, 722, 611, 833, 722, 778,
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 333, 278, 333, 584, 556,
    333, 556, 611, 556, 611, 556, 333, 611, 611, 278, 278, 556, 278, 889, 611, 611,
    611, 611, 389, 556, 333, 611, 556, 778, 556, 556, 500, 389, 280, 389, 584,
]
_ANCHOS = {chr(32 + i): w for i, w in enumerate(_ANCHOS_HELVETICA)}
_ANCHOS_NEGRITA = {chr(32 + i): w for i, w in enumerate(_ANCHOS_BOLD)}

# Columnas de la tabla: (x, ancho, alineacion).
COL_CODIGO = (MARGEN, 58.0, "left")
COL_DESC = (MARGEN + 62, 196.0, "left")
COL_CANT = (MARGEN + 262, 34.0, "right")
COL_PRECIO = (MARGEN + 300, 66.0, "right")
COL_STOCK = (MARGEN + 370, 40.0, "right")
COL_SUBTOTAL = (MARGEN + 414, 81.0, "right")


# --------------------------------------------------------------------------
# Texto
# --------------------------------------------------------------------------
def _ancho(texto: str, size: float = 10.0, bold: bool = False) -> float:
    """Ancho aproximado del texto en puntos."""
    tabla = _ANCHOS_NEGRITA if bold else _ANCHOS
    por_defecto = 611 if bold else 556
    total = sum(tabla.get(ch, por_defecto) for ch in (texto or ""))
    return total / 1000.0 * size


def _recortar(texto: str, size: float, bold: bool, ancho: float) -> str:
    """Recorta con puntos suspensivos si el texto no entra en el ancho."""
    texto = texto or ""
    if _ancho(texto, size, bold) <= ancho:
        return texto
    while texto and _ancho(texto + "...", size, bold) > ancho:
        texto = texto[:-1]
    return texto.rstrip() + "..."


def _envolver(texto: str, size: float, bold: bool, ancho: float) -> list[str]:
    """Corta un texto en lineas que entren en el ancho dado."""
    palabras, lineas, actual = (texto or "").split(), [], ""
    for palabra in palabras:
        prueba = f"{actual} {palabra}".strip()
        if _ancho(prueba, size, bold) <= ancho:
            actual = prueba
        else:
            if actual:
                lineas.append(actual)
            actual = palabra
    if actual:
        lineas.append(actual)
    return lineas or [""]


def _literal(texto: str) -> bytes:
    """Codifica un texto como literal PDF (WinAnsi, escapado)."""
    limpio = (texto or "").translate(_NORMALIZAR)
    datos = limpio.encode("cp1252", errors="replace")
    return (
        datos.replace(b"\\", b"\\\\")
        .replace(b"(", b"\\(")
        .replace(b")", b"\\)")
    )


def _texto_ops(
    x: float,
    y: float,
    texto: str,
    size: float = 10.0,
    bold: bool = False,
    color: tuple[float, float, float] | None = None,
    align: str = "left",
    ancho: float = 0.0,
) -> list[bytes]:
    """Operadores para dibujar una linea de texto (y = linea base desde arriba)."""
    if align == "right":
        x = x + ancho - _ancho(texto, size, bold)
    elif align == "center":
        x = x + (ancho - _ancho(texto, size, bold)) / 2
    ops: list[bytes] = []
    if color:
        ops.append(f"{color[0]:.3f} {color[1]:.3f} {color[2]:.3f} rg".encode())
    ops.append(
        b"BT /F"
        + (b"2" if bold else b"1")
        + f" {size:.2f} Tf 1 0 0 1 {x:.2f} {ALTO - y:.2f} Tm (".encode()
        + _literal(texto)
        + b") Tj ET"
    )
    if color:
        ops.append(f"{NEGRO[0]:.3f} {NEGRO[1]:.3f} {NEGRO[2]:.3f} rg".encode())
    return ops


def _rect_ops(
    x: float, y: float, ancho: float, alto: float, color: tuple[float, float, float]
) -> bytes:
    """Rectangulo relleno (y = borde superior desde arriba)."""
    return (
        f"{color[0]:.3f} {color[1]:.3f} {color[2]:.3f} rg "
        f"{x:.2f} {ALTO - y - alto:.2f} {ancho:.2f} {alto:.2f} re f "
        f"{NEGRO[0]:.3f} {NEGRO[1]:.3f} {NEGRO[2]:.3f} rg"
    ).encode()


def _linea_ops(x1: float, y: float, x2: float, color=GRIS_LINEA, grosor: float = 0.5) -> bytes:
    """Linea horizontal (y desde arriba)."""
    return (
        f"{color[0]:.3f} {color[1]:.3f} {color[2]:.3f} RG {grosor} w "
        f"{x1:.2f} {ALTO - y:.2f} m {x2:.2f} {ALTO - y:.2f} l S"
    ).encode()


# --------------------------------------------------------------------------
# Documento
# --------------------------------------------------------------------------
def _precio(valor) -> str:
    """Formatea un monto como entero con separador de miles (estilo CLP)."""
    try:
        return f"{int(valor):,}".replace(",", ".")
    except (TypeError, ValueError):
        return str(valor)


def _fecha(valor: str) -> str:
    """Fecha legible: 2026-10-22T15:26:20 -> 22-10-2026 15:26."""
    crudo = (valor or "").strip()
    if "T" in crudo:
        dia, resto = crudo.split("T", 1)
        partes = dia.split("-")
        if len(partes) == 3:
            return f"{partes[2]}-{partes[1]}-{partes[0]} {resto[:5]}"
    return crudo


class _Lienzo:
    """Paginas en construccion, con cursor vertical medido desde arriba."""

    def __init__(self) -> None:
        self.paginas: list[list[bytes]] = []
        self.ops: list[bytes] = []
        self.y = MARGEN

    # -- primitivas --------------------------------------------------------
    def texto(self, x, texto, size=10.0, bold=False, color=None, align="left", ancho=0.0):
        self.ops += _texto_ops(x, self.y, texto, size, bold, color, align, ancho)

    def linea(self, x1, x2, color=GRIS_LINEA, grosor=0.5):
        self.ops.append(_linea_ops(x1, self.y, x2, color, grosor))

    def salto(self, alto: float):
        self.y += alto

    def nueva_pagina(self):
        self.paginas.append(self.ops)
        self.ops = []
        self.y = MARGEN + 24

    # -- bloques -----------------------------------------------------------
    def cabecera(self, documento: dict, vehiculo: str, titulo: str):
        es_comprobante = documento.get("tipo") == "comprobante"
        self.y = MARGEN + 18
        self.texto(MARGEN, "REPUESTOS SUR", 19, bold=True)
        self.texto(MARGEN, titulo, 12, bold=True, color=GRIS, align="right", ancho=DERECHA - MARGEN)
        self.salto(12)
        self.texto(
            MARGEN,
            "Repuestos automotrices | Asistente de ventas",
            8.5,
            color=GRIS,
        )
        self.salto(10)
        self.linea(MARGEN, DERECHA, GRIS_LINEA, 0.8)

        # Datos del documento
        self.salto(24)
        self.texto(MARGEN, "Fecha", 8.5, bold=True, color=GRIS)
        self.texto(MARGEN + 62, _fecha(documento.get("fecha")), 9.5)
        self.salto(14)
        self.texto(MARGEN, "Cliente", 8.5, bold=True, color=GRIS)
        self.texto(MARGEN + 62, documento.get("cliente") or "no indicado", 9.5)
        if vehiculo or documento.get("vehiculo"):
            self.salto(14)
            self.texto(MARGEN, "Vehiculo", 8.5, bold=True, color=GRIS)
            self.texto(MARGEN + 62, vehiculo or documento.get("vehiculo"), 9.5)
        if es_comprobante and documento.get("referencia"):
            self.salto(14)
            self.texto(MARGEN, "Venta", 8.5, bold=True, color=GRIS)
            self.texto(MARGEN + 62, documento["referencia"], 9.5, bold=True)

        self.salto(30)
        self.cabecera_tabla()

    def cabecera_tabla(self):
        self.ops.append(_rect_ops(MARGEN, self.y - 12, DERECHA - MARGEN, 19, GRIS_FONDO))
        self.texto(COL_CODIGO[0] + 4, "Codigo", 8.5, bold=True)
        self.texto(COL_DESC[0], "Descripcion", 8.5, bold=True)
        self.texto(COL_CANT[0], "Cant.", 8.5, bold=True, align="right", ancho=COL_CANT[1])
        self.texto(COL_PRECIO[0], "Precio", 8.5, bold=True, align="right", ancho=COL_PRECIO[1])
        self.texto(COL_STOCK[0], "Stock", 8.5, bold=True, align="right", ancho=COL_STOCK[1])
        self.texto(COL_SUBTOTAL[0], "Subtotal", 8.5, bold=True, align="right", ancho=COL_SUBTOTAL[1])
        self.salto(8)
        self.linea(MARGEN, DERECHA, GRIS_LINEA, 0.8)
        self.salto(6)

    def fila(self, item: dict):
        cantidad = int(item.get("cantidad") or 1)
        precio = int(item.get("precio") or 0)
        subtotal = precio * cantidad
        stock = item.get("stock")
        descripcion = item.get("descripcion") or ""
        if item.get("stock_status") in ("critico", "agotado"):
            descripcion += " (STOCK BAJO)" if item["stock_status"] == "critico" else " (AGOTADO)"

        self.texto(COL_CODIGO[0] + 4, item.get("codigo") or "", 9, bold=True)
        self.texto(
            COL_DESC[0],
            _recortar(descripcion, 9, False, COL_DESC[1]),
            9,
        )
        self.texto(COL_CANT[0], str(cantidad), 9, align="right", ancho=COL_CANT[1])
        self.texto(COL_PRECIO[0], _precio(precio), 9, align="right", ancho=COL_PRECIO[1])
        self.texto(
            COL_STOCK[0],
            "" if stock is None else str(stock),
            9,
            color=ROJO if item.get("stock_status") in ("critico", "agotado") else None,
            align="right",
            ancho=COL_STOCK[1],
        )
        self.texto(COL_SUBTOTAL[0], _precio(subtotal), 9, align="right", ancho=COL_SUBTOTAL[1])
        self.salto(7)
        self.linea(MARGEN, DERECHA, GRIS_FONDO, 0.4)
        self.salto(11)

    def total(self, documento: dict):
        self.ops.append(_rect_ops(MARGEN, self.y - 12, DERECHA - MARGEN, 22, GRIS_FONDO))
        self.texto(MARGEN + 4, "TOTAL", 10, bold=True)
        self.texto(
            COL_SUBTOTAL[0],
            "$" + _precio(documento.get("total", 0)),
            11,
            bold=True,
            align="right",
            ancho=COL_SUBTOTAL[1],
        )
        self.salto(34)

    def bloque(self, titulo: str, texto: str, color=None, size=9):
        if not texto:
            return
        for i, linea in enumerate(_envolver(texto, size, False, DERECHA - MARGEN)):
            if i == 0 and titulo:
                self.ops += _texto_ops(MARGEN, self.y, titulo, size, True, color)
                self.ops += _texto_ops(MARGEN + _ancho(titulo + " ", size, True), self.y, linea, size, False, color)
            else:
                self.ops += _texto_ops(MARGEN, self.y, linea, size, False, color)
            self.salto(size + 3.5)
        self.salto(4)


def _pie(ops: list[bytes], numero: int, total: int) -> None:
    """Pie de pagina (se agrega al final, cuando se conoce el total)."""
    y = ALTO - 62  # linea de cierre, 62pt sobre el borde inferior
    ops.append(_linea_ops(MARGEN, y, DERECHA, GRIS_LINEA, 0.6))
    ops += _texto_ops(MARGEN, y + 10, "Repuestos Sur | Asistente de ventas", 8, False, GRIS)
    ops += _texto_ops(
        MARGEN,
        y + 10,
        f"Pagina {numero} de {total}",
        8,
        False,
        GRIS,
        align="right",
        ancho=DERECHA - MARGEN,
    )
    ops += _texto_ops(
        MARGEN,
        y + 22,
        "Precios y stock tomados del inventario de la tienda al momento de emitir el documento.",
        7,
        False,
        GRIS,
    )


def generar_pdf(documento: dict, vehiculo: str = "", mensaje: str = "") -> bytes:
    """Devuelve el PDF de una cotizacion o comprobante como bytes."""
    es_comprobante = documento.get("tipo") == "comprobante"
    titulo = "COMPROBANTE DE VENTA" if es_comprobante else "COTIZACION"

    lienzo = _Lienzo()
    lienzo.cabecera(documento, vehiculo, titulo)

    items = documento.get("items") or []
    for item in items:
        # Si no entra la fila y el total, se abre otra pagina y se repite la
        # cabecera de la tabla para que la continuacion se entienda sola.
        if lienzo.y > ALTO - MARGEN - 120:
            lienzo.nueva_pagina()
            lienzo.texto(MARGEN, f"{titulo} - {documento.get('cliente') or 'cliente'}", 10, bold=True, color=GRIS)
            lienzo.salto(18)
            lienzo.cabecera_tabla()
        lienzo.fila(item)

    # Si el total y los avisos no entran, se pasan a una hoja nueva.
    if lienzo.y > ALTO - MARGEN - 130:
        lienzo.nueva_pagina()
        lienzo.texto(
            MARGEN,
            f"{titulo} - {documento.get('cliente') or 'cliente'}",
            10,
            bold=True,
            color=GRIS,
        )
        lienzo.salto(22)

    lienzo.total(documento)

    avisos = documento.get("avisos") or []
    if avisos:
        lienzo.bloque("Avisos:", "; ".join(avisos), ROJO, 8.5)
    if mensaje:
        lienzo.bloque("", mensaje.strip(), NEGRO, 9)

    lienzo.salto(6)
    lienzo.linea(MARGEN, DERECHA, GRIS_LINEA, 0.6)
    lienzo.salto(14)
    lienzo.texto(MARGEN, "Documento generado automaticamente por el agente de Repuestos Sur.", 7.5, color=GRIS)

    paginas = lienzo.paginas + [lienzo.ops]
    for i, ops in enumerate(paginas, start=1):
        _pie(ops, i, len(paginas))

    contenidos = [b"\n".join(ops) for ops in paginas]
    return _ensamblar(contenidos, f"{titulo} - Repuestos Sur")


def guardar_pdf(
    documento: dict,
    destino: str | Path,
    vehiculo: str = "",
    mensaje: str = "",
) -> Path:
    """Escribe el PDF en ``destino`` y devuelve la ruta."""
    ruta = Path(destino)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(generar_pdf(documento, vehiculo, mensaje))
    return ruta


# --------------------------------------------------------------------------
# Ensamblado del archivo PDF
# --------------------------------------------------------------------------
def _ensamblar(contenidos: list[bytes], titulo: str) -> bytes:
    """Arma el PDF 1.4: catalogo, paginas, fuentes y tabla xref."""
    n = len(contenidos)
    # 1 catalogo, 2 pages, 3 y 4 fuentes, luego un par (page, content) por hoja
    ids_pagina = [5 + 2 * i for i in range(n)]
    ids_contenido = [6 + 2 * i for i in range(n)]
    id_info = 5 + 2 * n

    objetos: list[bytes] = []
    objetos.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{i} 0 R" for i in ids_pagina)
    objetos.append(f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode())
    objetos.append(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
        b"/Encoding /WinAnsiEncoding >>"
    )
    objetos.append(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold "
        b"/Encoding /WinAnsiEncoding >>"
    )
    for id_pagina, id_contenido, contenido in zip(ids_pagina, ids_contenido, contenidos):
        objetos.append(
            (
                f"<< /Type /Page /Parent 2 0 R "
                f"/MediaBox [0 0 {ANCHO:.2f} {ALTO:.2f}] "
                f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
                f"/Contents {id_contenido} 0 R >>"
            ).encode()
        )
        objetos.append(
            b"<< /Length " + str(len(contenido)).encode() + b" >>\nstream\n"
            + contenido
            + b"\nendstream"
        )
    objetos.append(
        b"<< /Title (" + _literal(titulo) + b") /Producer (Repuestos Sur) "
        b"/Creator (Repuestos Sur - Asistente de ventas) >>"
    )

    salida = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for numero, objeto in enumerate(objetos, start=1):
        offsets.append(len(salida))
        salida += f"{numero} 0 obj\n".encode() + objeto + b"\nendobj\n"

    inicio_xref = len(salida)
    total_objetos = len(objetos) + 1
    salida += f"xref\n0 {total_objetos}\n".encode()
    salida += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        salida += f"{offset:010d} 00000 n \n".encode()
    salida += (
        f"trailer\n<< /Size {total_objetos} /Root 1 0 R /Info {id_info} 0 R >>\n"
        f"startxref\n{inicio_xref}\n%%EOF\n"
    ).encode()
    return bytes(salida)
