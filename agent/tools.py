"""Tools del agente: consulta, escritura y memoria (Requisito A - IE1/IE2).

El LLM decide que herramienta usar y con que argumentos; nunca accede directo
al CSV ni a Chroma. Cada tool devuelve texto plano para que el modelo pueda
razonar sobre el resultado.
"""
from __future__ import annotations

import json
import re
from datetime import datetime

from langchain_core.tools import tool

from agent.memory import LongTermMemory
from tools.inventory_lookup import (
    ROOT,
    diagnose_missing,
    find_by_code,
    format_part,
    load_inventory,
    search_parts,
    stock_status,
    year_matches,
)

EXPORT_DIR = ROOT / "data" / "exports"

_inventory_cache: list[dict] | None = None


def get_inventory() -> list[dict]:
    """Inventario en memoria (se relee solo si cambio el archivo)."""
    global _inventory_cache
    if _inventory_cache is None:
        _inventory_cache = load_inventory()
    return _inventory_cache


def reload_inventory() -> None:
    global _inventory_cache
    _inventory_cache = None


# --------------------------------------------------------------------------
# Tools de consulta
# --------------------------------------------------------------------------
@tool
def buscar_repuesto(marca: str, modelo: str, anio: str, tipo_repuesto: str = "") -> str:
    """Busca en el inventario de la tienda repuestos COMPATIBLES con un vehiculo.

    Usala siempre que el cliente pida un repuesto o pregunte precios/stock.
    marca, modelo y anio son obligatorios (ej: 'Suzuki', 'Swift', '2015').
    tipo_repuesto es opcional y filtra por tipo de pieza (ej: 'alternador',
    'pastillas de freno', 'kit embrague', 'filtro').

    Devuelve el codigo, descripcion, precio y stock de cada coincidencia, o el
    motivo exacto por el que no hay resultados (falta un dato, anio fuera de
    rango, modelo inexistente, etc.). Nunca inventes repuestos a partir de esto.
    """
    inventory = get_inventory()
    results = search_parts(inventory, marca, modelo, anio, tipo=tipo_repuesto)
    if not results:
        # Si el filtro por tipo no matcheo, reintenta sin el filtro para
        # distinguir "no existe ese tipo" de "no hay para ese vehiculo".
        if tipo_repuesto:
            genericos = search_parts(inventory, marca, modelo, anio)
            if genericos:
                lineas = "\n".join(f"- {format_part(p)}" for p in genericos)
                return (
                    f"No hay '{tipo_repuesto}' para {marca} {modelo} {anio}. "
                    f"Si existen estos repuestos para ese vehiculo:\n{lineas}"
                )
        return diagnose_missing(inventory, marca, modelo, anio)

    lineas = "\n".join(f"- {format_part(p)}" for p in results)
    criticos = [p["codigo"] for p in results if stock_status(p) != "ok"]
    alerta = (
        "\nALERTA DE STOCK (avisar al cliente): " + ", ".join(criticos)
        if criticos
        else ""
    )
    return f"{len(results)} repuesto(s) para {marca} {modelo} {anio}:\n{lineas}{alerta}"


@tool
def buscar_en_manual(consulta: str) -> str:
    """Recupera especificaciones tecnicas de los manuales PDF de repuestos (RAG).

    Usala para dudas tecnicas: amperaje, medidas, torque, instalacion,
    periodicidad de mantencion, que incluye un kit, etc.
    ``consulta`` debe ser la pregunta tecnica (ej: 'especificaciones alternador
    12V 90A amperaje medidas').

    Devuelve fragmentos del manual con el archivo y la pagina de origen.
    Si no hay coincidencia responde 'no tengo informacion suficiente' en vez
    de inventar especificaciones.
    """
    try:
        from agent.rag import COL_MANUALS, ensure_index, search
    except Exception as exc:
        return f"No puedo consultar los manuales ahora ({exc.__class__.__name__})."
    try:
        ensure_index()
        hits = search(COL_MANUALS, consulta, k=4)
    except Exception as exc:
        return f"No pude consultar los manuales ({exc.__class__.__name__}: {exc})."

    if not hits:
        return (
            f"No tengo informacion suficiente en los manuales para: '{consulta}'. "
            "No inventes especificaciones; indicale al cliente que falta documentacion."
        )
    bloques = []
    for h in hits:
        meta = h["metadatos"]
        bloques.append(
            f"[Fuente: {meta.get('source')} - pagina {meta.get('page')}] "
            f"(relevancia {1 - h['distancia']:.2f})\n{h['documento']}"
        )
    return "Fragmentos de los manuales tecnicos:\n\n" + "\n\n".join(bloques)


@tool
def verificar_compatibilidad(codigo: str, vehiculo: str) -> str:
    """Verifica si el repuesto con ese CODIGO (ej: 'ALT-01') sirve para un vehiculo.

    Confirma contra el inventario si el repuesto es compatible con el vehiculo
    indicado (ej: 'Kia Rio 4 2018'). Devuelve la fila completa del repuesto y
    el veredicto de compatibilidad.
    """
    inventory = get_inventory()
    item = find_by_code(inventory, codigo)
    if item is None:
        codigos = ", ".join(i["codigo"] for i in inventory)
        return f"No existe el codigo '{codigo}' en el inventario. Codigos validos: {codigos}."

    texto_vehiculo = (vehiculo or "").lower()
    compat = item["vehiculos_compatibles"].lower()
    palabras = [p for p in re.split(r"\W+", texto_vehiculo) if len(p) >= 3]
    coincidencias = [p for p in palabras if p in compat]
    # Si el vehiculo trae un anio, ademas debe caer dentro de un rango valido.
    anio = re.search(r"\b(?:19|20)\d{2}\b", texto_vehiculo)
    anio_ok = year_matches(compat, int(anio.group())) if anio else True
    coincide = bool(coincidencias) and anio_ok

    veredicto = (
        f"SI es compatible con {vehiculo}."
        if coincide
        else f"NO hay registro de compatibilidad con {vehiculo} segun el inventario."
    )
    return (
        f"{veredicto}\nRepuesto: {format_part(item)}\n"
        f"Compatibilidad registrada: {item['vehiculos_compatibles']}"
    )


# --------------------------------------------------------------------------
# Tools de memoria (escritura / lectura de largo plazo)
# --------------------------------------------------------------------------
@tool
def recordar_dato(dato: str, categoria: str = "general") -> str:
    """Guarda en la memoria de LARGO PLAZO un dato importante del cliente.

    Usala cuando el cliente te diga algo que deba recordarse entre sesiones:
    su vehiculo ('mi auto es un Suzuki Swift 2015'), preferencias, presupuesto,
    compras anteriores. categoria ej: 'vehiculo', 'preferencia', 'compra'.
    NO guardes saludos ni datos que solo sirven para esta conversacion.
    """
    try:
        registro = LongTermMemory.record(dato, categoria=categoria)
    except Exception as exc:
        return f"No pude guardar el dato ({exc.__class__.__name__}: {exc})."
    return f"Recordado [{registro['categoria']}]: {registro['dato']} (id {registro['id']})."


@tool
def recuperar_memoria(consulta: str) -> str:
    """Busca en la memoria de LARGO PLAZO lo que se haya recordado de clientes.

    Usala al inicio de una conversacion o cuando necesites saber quien es el
    cliente, que vehiculo tiene o que compro antes. ``consulta`` ej: 'vehiculo
    del cliente', 'compras anteriores'. Si no hay nada guardado, lo dice.
    """
    try:
        hits = LongTermMemory.search(consulta, k=5)
    except Exception as exc:
        return f"No pude consultar la memoria ({exc.__class__.__name__}: {exc})."
    if not hits:
        return "La memoria de largo plazo esta vacia: todavia no hay datos del cliente."
    lineas = [f"- {h['dato']}" for h in hits]
    return "Datos recordados del cliente:\n" + "\n".join(lineas)


# --------------------------------------------------------------------------
# Tool de escritura
# --------------------------------------------------------------------------
@tool
def exportar_cotizacion(codigos: list[str], cliente: str = "") -> str:
    """Escribe en disco la cotizacion de los repuestos indicados (escritura real).

    ``codigos`` es la lista de codigos del inventario a cotizar (ej:
    ['ALT-01', 'FLT-01']). Crea un archivo JSON en data/exports/ con fecha,
    cliente, detalle y total. Usala SOLO cuando el cliente pida cotizar,
    guardar o enviar la cotizacion.
    """
    inventory = get_inventory()
    items, faltantes = [], []
    for code in codigos:
        item = find_by_code(inventory, str(code))
        if item is None:
            faltantes.append(str(code))
        else:
            items.append(
                {
                    "codigo": item["codigo"],
                    "descripcion": item["descripcion"],
                    "precio": int(item["precio"]),
                    "stock": int(item["stock"]),
                    "stock_status": stock_status(item),
                }
            )
    if not items:
        return f"Ningun codigo es valido ({', '.join(codigos) or 'vacio'}). No se exporto nada."

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = EXPORT_DIR / f"cotizacion_{stamp}.json"
    documento = {
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "cliente": cliente or "no indicado",
        "items": items,
        "total": sum(i["precio"] for i in items),
        "avisos": (
            [f"codigo inexistente: {c}" for c in faltantes]
            + [f"stock bajo: {i['codigo']}" for i in items if i["stock_status"] != "ok"]
        ),
    }
    path.write_text(json.dumps(documento, ensure_ascii=False, indent=2), encoding="utf-8")
    aviso = f" Avisos: {'; '.join(documento['avisos'])}." if documento["avisos"] else ""
    return (
        f"Cotizacion guardada en {path} con {len(items)} item(s) "
        f"por ${documento['total']}.{aviso}"
    )


ALL_TOOLS = [
    buscar_repuesto,
    buscar_en_manual,
    verificar_compatibilidad,
    recordar_dato,
    recuperar_memoria,
    exportar_cotizacion,
]
