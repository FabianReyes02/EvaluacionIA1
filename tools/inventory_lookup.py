"""Busqueda y diagnostico sobre data/internal/inventory.csv.

Fuente unica valida de verdad para repuestos: precio, stock y compatibilidad.
Todo lo que el agente afirma sobre un repuesto debe poder trazarse hasta aqui.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INVENTORY_PATH = ROOT / "data" / "internal" / "inventory.csv"

# Stock menor a esto genera alerta explicita (regla de seguridad del encargo).
STOCK_CRITICO = 5


def load_inventory(path: str | Path = INVENTORY_PATH) -> list[dict]:
    """Lee el CSV y devuelve una lista de filas como dict."""
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def year_matches(compat: str, year: int) -> bool:
    """True si el anio cae dentro de uno de los rangos en la cadena de compatibilidad."""
    for lo, hi in re.findall(r"(\d{4})\s*-\s*(\d{4})", compat):
        if int(lo) <= year <= int(hi):
            return True
    return False


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
            haystack = f"{item['descripcion']} {item['categoria']}".lower()
            if not any(p in haystack for p in _tokens(tipo)):
                continue
        results.append(item)
    return results


def _tokens(text: str) -> list[str]:
    """Palabras con minimo 3 letras, para comparar tipo de repuesto."""
    return [t for t in re.findall(r"[\wáéíóúñ]+", text.lower()) if len(t) >= 3]


def find_by_code(inventory: list[dict], code: str) -> dict | None:
    """Devuelve la fila con ese codigo (ignora mayusculas) o None."""
    code = (code or "").strip().upper()
    for item in inventory:
        if item["codigo"].strip().upper() == code:
            return item
    return None


def stock_status(item: dict) -> str:
    """'agotado' | 'critico' | 'ok' segun el stock de la fila."""
    stock = int(item["stock"])
    if stock <= 0:
        return "agotado"
    if stock < STOCK_CRITICO:
        return "critico"
    return "ok"


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
