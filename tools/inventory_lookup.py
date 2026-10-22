"""Busqueda y diagnostico sobre el inventario de la tienda.

El catalogo vive en ``data/internal/inventory.csv`` (descripcion, marca, precio
y compatibilidad) y el **stock real** vive en la base de datos interna
(``tools/db.py``): ``load_inventory`` devuelve el catalogo del CSV con el stock
que quedo en la BD, y ``sincronizar_stock_csv`` re-escribe el CSV despues de
cada venta para que el archivo y la base de datos digan lo mismo.

Todo lo que el agente afirma sobre un repuesto debe poder trazarse hasta aqui.
"""
from __future__ import annotations

import csv
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _ruta_inventario() -> Path:
    """Ruta del CSV del inventario (variable de entorno ``INVENTORY_PATH``).

    Las rutas relativas se resuelven contra la raiz del proyecto. Los evals
    apuntan a una copia para no modificar el inventario real.
    """
    raw = (os.getenv("INVENTORY_PATH") or "").strip()
    if not raw:
        return ROOT / "data" / "internal" / "inventory.csv"
    ruta = Path(raw)
    if not ruta.is_absolute():
        ruta = ROOT / ruta
    return ruta


INVENTORY_PATH = _ruta_inventario()

# Stock menor a esto genera alerta explicita (regla de seguridad del encargo).
STOCK_CRITICO = 5


def load_inventory(path: str | Path = INVENTORY_PATH) -> list[dict]:
    """Lee el inventario y devuelve una lista de filas como dict.

    El catalogo viene del CSV y el stock de la base de datos interna (que es la
    verdad): si la BD todavia no existe, se crea y se siembra desde el CSV.
    """
    with open(path, encoding="utf-8") as f:
        filas = list(csv.DictReader(f))
    try:
        from tools.db import stock_por_codigo

        stock = stock_por_codigo()
    except Exception:
        stock = {}
    for fila in filas:
        if fila.get("codigo") in stock:
            fila["stock"] = str(stock[fila["codigo"]])
    return filas


def sincronizar_stock_csv(stock: dict[str, int], path: str | Path = INVENTORY_PATH) -> bool:
    """Re-escribe la columna ``stock`` del CSV con el stock real de la BD.

    Se llama despues de cada venta para que el archivo versionado y la base de
    datos no se contradigan. Solo cambia la columna de stock: el resto del
    catalogo (descripcion, marca, precio, compatibilidad) queda intacto.

    Devuelve True si el CSV quedo escrito.
    """
    if not stock:
        return False
    path = Path(path)
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        campos = list(reader.fieldnames or [])
        filas = list(reader)
    if "codigo" not in campos or "stock" not in campos:
        return False

    cambios = 0
    for fila in filas:
        codigo = fila.get("codigo", "")
        if codigo in stock and str(fila.get("stock")) != str(stock[codigo]):
            fila["stock"] = str(stock[codigo])
            cambios += 1
    if not cambios:
        return False

    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        writer.writerows(filas)
    os.replace(tmp, path)
    return True


def year_matches(compat: str, year: int) -> bool:
    """True si el anio cae dentro de uno de los rangos en la cadena de compatibilidad."""
    for lo, hi in re.findall(r"(\d{4})\s*-\s*(\d{4})", compat):
        if int(lo) <= year <= int(hi):
            return True
    return False


def _haystack(item: dict) -> str:
    """Texto donde se busca el tipo de repuesto (descripcion + categoria)."""
    return f"{item['descripcion']} {item['categoria']}".lower()


def coincide_tipo(item: dict, tipo: str) -> bool:
    """True si la pieza cumple TODOS los tokens del tipo pedido.

    ``search_parts`` filtra con coincidencia parcial (basta con que un token
    coincida) para no perder resultados; esta funcion distingue el match
    exacto del aproximado (ej: 'filtro de aceite' -> 'filtro de aire motor'
    cumple solo 'filtro').
    """
    tokens = _tokens(tipo)
    if not tokens:
        return True
    hay = _haystack(item)
    return all(t in hay for t in tokens)


def search_parts(
    inventory: list[dict],
    brand: str,
    model: str,
    year: str,
    tipo: str = "",
) -> list[dict]:
    """Busca repuestos cuyo vehiculos_compatibles contengan marca, modelo y anio.

    ``tipo`` es opcional: si viene, filtra por coincidencia parcial en la
    descripcion/categoria (ej: "alternador", "freno").
    """
    try:
        year_int = int(str(year).strip())
    except ValueError:
        return []
    if not brand or not model:
        return []
    results = []
    for item in inventory:
        compat = item["vehiculos_compatibles"].lower()
        if not (brand.lower() in compat and model.lower() in compat):
            continue
        if not year_matches(compat, year_int):
            continue
        if tipo:
            haystack = _haystack(item)
            if not any(p in haystack for p in _tokens(tipo)):
                continue
        results.append(item)
    return results


def _tokens(text: str) -> list[str]:
    """Palabras con minimo 3 letras, para comparar tipo de repuesto."""
    return [t for t in re.findall(r"[\wáéíóúñ]+", text.lower()) if len(t) >= 3]


def normalizar_codigo(code: str) -> str:
    """Normaliza un codigo de repuesto para poder compararlo con el CSV.

    Los LLM escriben a veces el guion con variantes Unicode (U+2010 a U+2015,
    U+2212) en vez del guion ASCII, o meten espacios ("ALT - 01"). Sin esta
    normalizacion el codigo no existiria en el inventario y la cotizacion
    saldria vacia.
    """
    texto = (code or "").strip().upper()
    for dash in "\u2010\u2011\u2012\u2013\u2014\u2015\u2212":
        texto = texto.replace(dash, "-")
    return re.sub(r"\s*-\s*", "-", texto).strip()


def find_by_code(inventory: list[dict], code: str) -> dict | None:
    """Devuelve la fila con ese codigo (ignora mayusculas y guiones) o None."""
    code = normalizar_codigo(code)
    for item in inventory:
        if normalizar_codigo(item["codigo"]) == code:
            return item
    return None


def compatibilidad_vehiculo(item: dict, vehiculo: str) -> dict:
    """Contrasta un repuesto con un vehiculo-describedo.

    Devuelve el detalle del cruce contra ``vehiculos_compatibles``:

        {"coincide": bool, "anio": int|None, "anio_ok": bool, "palabras": [...]}

    ``coincide`` es True solo si el modelo del vehiculo aparece en la
    compatibilidad registrada y, si el vehiculo trae anio, ese anio cae dentro
    de los rangos de la pieza.
    """
    texto_vehiculo = (vehiculo or "").lower()
    compat = (item.get("vehiculos_compatibles") or "").lower()
    palabras = [p for p in re.split(r"\W+", texto_vehiculo) if len(p) >= 3]
    coincidencias = [p for p in palabras if p in compat]
    anio = re.search(r"\b(?:19|20)\d{2}\b", texto_vehiculo)
    anio_int = int(anio.group()) if anio else None
    anio_ok = year_matches(compat, anio_int) if anio_int else True
    return {
        "coincide": bool(coincidencias) and anio_ok,
        "anio": anio_int,
        "anio_ok": anio_ok,
        "palabras": coincidencias,
    }


def estado_stock(stock: int) -> str:
    """'agotado' | 'critico' | 'ok' a partir de una cantidad."""
    try:
        valor = int(stock)
    except (TypeError, ValueError):
        return "ok"
    if valor <= 0:
        return "agotado"
    if valor < STOCK_CRITICO:
        return "critico"
    return "ok"


def stock_status(item: dict) -> str:
    """'agotado' | 'critico' | 'ok' segun el stock de la fila."""
    return estado_stock(item["stock"])


def get_catalog_summary(inventory: list[dict]) -> str:
    """Resume los vehiculos con repuestos a partir del CSV (fuente unica valida)."""
    seen = []
    for item in inventory:
        for chunk in item["vehiculos_compatibles"].split(";"):
            chunk = chunk.strip()
            if chunk and chunk.lower() != "varios (ver manual)" and chunk not in seen:
                seen.append(chunk)
    if not seen:
        return "(inventario vacio)"
    return "\n".join(f"- {c}" for c in seen)


def diagnose_missing(inventory: list[dict], brand: str, model: str, year: str) -> str:
    """Mensaje especifico: indica si falta la marca, el modelo o el anio en el inventario."""
    brand = (brand or "").strip()
    model = (model or "").strip()
    year = (year or "").strip()

    faltantes = []
    if not brand:
        faltantes.append("marca")
    if not model:
        faltantes.append("modelo")
    if not year:
        faltantes.append("anio")
    if faltantes:
        return (
            f"No hay repuestos para mostrar porque falta ingresar: {', '.join(faltantes)}. "
            f"Por favor indica marca, modelo y anio (ej: Suzuki Swift 2015)."
        )

    try:
        year_int = int(year)
        anio_valido = 1900 <= year_int <= 2030
    except ValueError:
        return (
            f"No hay repuestos para el anio '{year}' porque no es un anio valido. "
            f"Ingresa el anio con 4 digitos (ej: 2015)."
        )
    if not anio_valido:
        return (
            f"No hay repuestos para el anio '{year}' porque esta fuera de rango. "
            f"Ingresa un anio valido con 4 digitos (ej: 2015)."
        )

    brand_found = any(brand.lower() in item["vehiculos_compatibles"].lower() for item in inventory)
    if not brand_found:
        return (
            f"No hay repuestos para la marca '{brand}' en el inventario. "
            f"Revisa la escritura o consulta por otra marca disponible."
        )

    model_found = any(
        brand.lower() in item["vehiculos_compatibles"].lower()
        and model.lower() in item["vehiculos_compatibles"].lower()
        for item in inventory
    )
    if not model_found:
        return (
            f"No hay repuestos para el modelo '{brand} {model}' en el inventario. "
            f"La marca '{brand}' si tiene repuestos, pero no para ese modelo. "
            f"Revisa la escritura del modelo."
        )

    # Marca y modelo existen, falla el anio: mostrar rangos disponibles.
    # Se filtran solo los fragmentos que corresponden a ese marca+modelo
    # (el CSV puede listar varios vehiculos por fila separados con ";").
    rangos = []
    for item in inventory:
        for chunk in item["vehiculos_compatibles"].split(";"):
            chunk = chunk.strip()
            if brand.lower() in chunk.lower() and model.lower() in chunk.lower():
                rangos.append(chunk)
    rangos_txt = "; ".join(sorted(set(rangos))) or "sin rangos registrados"
    return (
        f"No hay repuestos para el anio '{year}' del {brand} {model} en el inventario. "
        f"Compatibilidades registradas para ese modelo: {rangos_txt}."
    )


def format_part(item: dict) -> str:
    """Fila del inventario en una linea legible, con alerta de stock si corresponde."""
    status = stock_status(item)
    alerta = ""
    if status == "agotado":
        alerta = " [AGOTADO]"
    elif status == "critico":
        alerta = " [STOCK BAJO]"
    return (
        f"[{item['codigo']}] {item['descripcion']} - ${item['precio']} - "
        f"Stock: {item['stock']}{alerta}"
    )


def format_plain(
    parts: list[dict],
    brand: str,
    model: str,
    year: str,
    inventory: list[dict] | None = None,
) -> str:
    """Fallback sin IA: muestra los repuestos en texto plano."""
    if not parts:
        if inventory is not None:
            return diagnose_missing(inventory, brand, model, year)
        return f"No se encontraron repuestos para {brand} {model} {year}."
    lines = [f"Repuestos para {brand} {model} {year}:"]
    for p in parts:
        lines.append(f"  {format_part(p)}")
    return "\n".join(lines)
