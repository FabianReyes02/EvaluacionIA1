"""Guardrails de seguridad: verificacion POST-LLM, no solo prompt (Fase 4).

Regla del encargo: el agente nunca sugiere un repuesto sin respaldo en el
inventario, y el stock critico siempre genera una alerta explicita. Por eso el
texto que produce el modelo se re-verifica contra el CSV antes de mostrarse.
"""
from __future__ import annotations

import re

from tools.inventory_lookup import find_by_code, stock_status

# Codigos tipo ALT-01, FLT-02, EMP-05...
CODIGO_RE = re.compile(r"\b([A-Za-z]{2,4}-\d{2,3})\b")


def extract_codes(text: str) -> list[str]:
    """Codigos de repuesto mencionados en la respuesta del modelo."""
    seen = []
    for code in CODIGO_RE.findall(text or ""):
        up = code.upper()
        if up not in seen:
            seen.append(up)
    return seen


def apply(text: str, inventory: list[dict]) -> tuple[str, list[str]]:
    """Verifica ``text`` contra el inventario. Devuelve (texto_final, violaciones).

    Violaciones son strings legibles que quedan en la traza:
      - codigo inexistente -> se marca en la respuesta
      - stock bajo/agotado sin alerta -> se agrega la alerta
    """
    if not text:
        return text, []
    violations: list[str] = []
    clean = text

    # 1) Ningun codigo puede ser inventado.
    for code in extract_codes(text):
        item = find_by_code(inventory, code)
        if item is None:
            violations.append(f"codigo_inexistente:{code}")
            clean = clean.replace(code, f"{code} (no verificado)")
            clean += (
                f"\n\n[Guardrail] No puedo confirmar el repuesto {code}: "
                "no existe en el inventario de la tienda."
            )

    # 2) Todo repuesto con stock critico o agotado debe llevar alerta.
    for code in extract_codes(clean):
        item = find_by_code(inventory, code)
        if item is None or stock_status(item) == "ok":
            continue
        if _is_catalog_listing(clean, code) or _has_stock_alert(clean, code):
            continue
        status = stock_status(item)
        detalle = (
            "esta agotado"
            if status == "agotado"
            else f"quedan solo {item['stock']} unidades (stock bajo)"
        )
        violations.append(f"stock_sin_alerta:{code}")
        clean += f"\n[Alerta de stock] {code}: {detalle}."

    return clean, violations


def _is_catalog_listing(text: str, code: str) -> bool:
    """True si el codigo aparece en una linea que enumera 3+ codigos.

    Eso es un listado del catalogo (ej. "codigos validos: ALT-01, ALT-02..."),
    no una recomendacion: ahi no corresponde alerta de stock.
    """
    for line in text.splitlines():
        if re.search(re.escape(code), line, re.IGNORECASE):
            if len(extract_codes(line)) >= 3:
                return True
    return False


def _has_stock_alert(text: str, code: str) -> bool:
    """True si cerca del codigo aparece una alerta de stock."""
    for m in re.finditer(re.escape(code), text, re.IGNORECASE):
        ventana = text[max(0, m.start() - 120): m.end() + 160].lower()
        if any(p in ventana for p in ("stock bajo", "stock critico", "agotado", "sin stock", "stock: 0", "quedan")):
            return True
    # Tambien vale si la alerta esta en una linea aparte referida al codigo.
    return bool(re.search(rf"{re.escape(code)}[^\n]*\[(AGOTADO|STOCK BAJO)\]", text, re.IGNORECASE))


def not_found_reply() -> str:
    """Respuesta canonica cuando no hay respaldo en la fuente (regla no negociable)."""
    return (
        "No tengo informacion suficiente para recomendarte ese repuesto: "
        "no esta en el inventario ni en los manuales de la tienda. "
        "Prefiero no improvisar. Si me das marca, modelo y anio del vehiculo, "
        "vuelvo a buscar."
    )
