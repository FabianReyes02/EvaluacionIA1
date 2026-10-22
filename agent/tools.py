"""Tools del agente: consulta, escritura y memoria (Requisito A - IE1/IE2).

El LLM decide que herramienta usar y con que argumentos; nunca accede directo
al CSV ni a Chroma. Cada tool devuelve texto plano para que el modelo pueda
razonar sobre el resultado.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from langchain_core.tools import tool

from agent.memory import LongTermMemory
from tools.email_sender import (
    enviar_cotizacion_documento,
    formatear_precio,
    validar_email,
)
from tools.inventory_lookup import (
    ROOT,
    coincide_tipo,
    compatibilidad_vehiculo,
    diagnose_missing,
    estado_stock,
    find_by_code,
    format_part,
    load_inventory,
    search_parts,
    stock_status,
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
    if tipo_repuesto and results:
        exactos = [p for p in results if coincide_tipo(p, tipo_repuesto)]
        if not exactos:
            # Solo hay coincidencias PARCIALES (ej: 'filtro de aceite' ->
            # 'filtro de aire motor' cumple solo 'filtro'). Se avisa para que el
            # agente cite el codigo como alternativa y no lo presente como el
            # repuesto exacto que pidio el cliente.
            lineas = "\n".join(f"- {format_part(p)}" for p in results)
            codigos = ", ".join(p["codigo"] for p in results)
            return (
                f"No hay '{tipo_repuesto}' exacto para {marca} {modelo} {anio}. "
                f"La coincidencia mas cercana en el inventario es:\n{lineas}\n"
                f"Cita el codigo ({codigos}) como alternativa y aclara al cliente "
                f"que no es exactamente el tipo que pidio."
            )
        results = exactos
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

    cruce = compatibilidad_vehiculo(item, vehiculo)
    veredicto = (
        f"SI es compatible con {vehiculo}."
        if cruce["coincide"]
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
# Cotizacion: documento en disco y envio por correo
# --------------------------------------------------------------------------
def _construir_cotizacion(
    codigos: list[str],
    cliente: str = "",
    vehiculo: str = "",
) -> tuple[dict, list[str]]:
    """Arma el documento de cotizacion desde el CSV (fuente unica de verdad).

    Devuelve (documento, codigos_faltantes). Precios y stock se leen siempre
    del inventario, nunca de lo que dijo el modelo.
    """
    inventory = get_inventory()
    items, faltantes = [], []
    for code in codigos or []:
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
    documento = {
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "cliente": cliente or "no indicado",
        "vehiculo": vehiculo or "no indicado",
        "items": items,
        "total": sum(i["precio"] for i in items),
        "avisos": (
            [f"codigo inexistente: {c}" for c in faltantes]
            + [f"stock bajo: {i['codigo']}" for i in items if i["stock_status"] != "ok"]
        ),
    }
    return documento, faltantes


def _guardar_cotizacion(documento: dict) -> Path:
    """Escribe el JSON de la cotizacion en data/exports/ y devuelve la ruta."""
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = EXPORT_DIR / f"cotizacion_{stamp}.json"
    path.write_text(json.dumps(documento, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


@tool
def exportar_cotizacion(codigos: list[str], cliente: str = "") -> str:
    """Escribe en disco la cotizacion de los repuestos indicados (escritura real).

    ``codigos`` es la lista de codigos del inventario a cotizar (ej:
    ['ALT-01', 'FLT-01']). Crea un archivo JSON en data/exports/ con fecha,
    cliente, detalle y total. Usala SOLO cuando el cliente pida cotizar,
    guardar o enviar la cotizacion.
    """
    documento, _ = _construir_cotizacion(codigos, cliente)
    if not documento["items"]:
        return (
            f"Ningun codigo es valido ({', '.join(codigos) or 'vacio'}). "
            "No se exporto nada."
        )

    path = _guardar_cotizacion(documento)
    avisos = documento["avisos"]
    aviso = f" Avisos: {'; '.join(avisos)}." if avisos else ""
    return (
        f"Cotizacion guardada en {path} con {len(documento['items'])} item(s) "
        f"por ${documento['total']}.{aviso}"
    )


@tool
def enviar_cotizacion_email(
    codigos: list[str],
    email_cliente: str,
    cliente: str = "",
    vehiculo: str = "",
    mensaje: str = "",
) -> str:
    """Envia por correo electronico la cotizacion de los repuestos indicados.

    Usala cuando el cliente pida ENVIAR la cotizacion por correo (ej: "mandame
    la cotizacion a juan@correo.com"). ``codigos`` son los codigos del
    inventario a cotizar (ej: ['ALT-01']) y ``email_cliente`` la direccion de
    destino. ``vehiculo`` y ``mensaje`` son opcionales.

    El cuerpo del correo se arma con los precios y el stock del INVENTORIO,
    nunca con lo que diga el modelo. Si el envio por SMTP no esta configurado,
    la cotizacion queda PREPARADA en un archivo .eml y NO se sale a internet:
    en ese caso informa que quedo preparada, jamas que fue enviada.

    Si el cliente no dio su direccion de correo, NO la inventes ni la deduzcas:
    pidela primero y despues llama esta herramienta.
    """
    ok, motivo = validar_email(email_cliente)
    if not ok:
        return (
            f"No puedo enviar la cotizacion por correo: {motivo}. "
            "Pidele al cliente su direccion de correo (ej: juan@correo.com) "
            "y vuelve a llamar esta herramienta."
        )

    documento, _ = _construir_cotizacion(codigos, cliente, vehiculo)
    if not documento["items"]:
        return (
            f"Ningun codigo es valido ({', '.join(codigos or []) or 'vacio'}). "
            "No se envio nada."
        )

    path = _guardar_cotizacion(documento)
    resultado = enviar_cotizacion_documento(
        documento,
        email_cliente.strip(),
        vehiculo=vehiculo,
        mensaje=mensaje,
        adjunto=path.read_bytes(),
        nombre_adjunto=path.name,
    )

    items = len(documento["items"])
    total = formatear_precio(documento["total"])
    avisos = documento["avisos"]
    detalle_avisos = f" Avisos: {'; '.join(avisos)}." if avisos else ""

    if resultado["enviado"]:
        return (
            f"Cotizacion ENVIADA a {email_cliente.strip()} con {items} item(s) "
            f"por ${total}.{detalle_avisos} (Copia de la cotizacion en {path})"
        )
    if resultado["ruta"]:
        return (
            f"Cotizacion PREPARADA, NO se envio: {resultado['detalle']} "
            f"Contiene {items} item(s) por ${total}.{detalle_avisos} "
            "Informa al cliente que quedo lista y pendiente de envio."
        )
    return (
        f"No pude enviar la cotizacion a {email_cliente.strip()}: "
        f"{resultado['detalle']} La cotizacion quedo guardada en {path}."
        f"{detalle_avisos}"
    )


# --------------------------------------------------------------------------
# Venta: registra la venta en la base de datos interna y descuenta el stock
# --------------------------------------------------------------------------
@tool
def registrar_venta(
    codigos: list[str],
    cantidades: list[int] | None = None,
    cliente: str = "",
    email_cliente: str = "",
    vehiculo: str = "",
    enviar_comprobante: bool = False,
) -> str:
    """Registra una VENTA real: descuenta el stock del inventario del cliente.

    Usala SOLO cuando el cliente confirme la compra ("lo llevo", "confirmo la
    compra", "proceda con la venta"). ``codigos`` son los codigos del
    inventario (ej: ['ALT-01']) y ``cantidades`` es opcional (por defecto 1 de
    cada uno). El descuento se hace en la base de datos interna de la tienda
    (data/internal/tienda.db) y el inventario queda sincronizado.

    Si no hay stock suficiente, NO registra nada y dice exactamente que falta.
    Si ``enviar_comprobante`` es True y hay ``email_cliente``, manda el
    comprobante de la venta por correo.

    Devuelve la referencia de la venta, el total y como quedo el stock.
    """
    if not codigos:
        return (
            "No puedo registrar la venta: no indicaste ningun codigo de repuesto. "
            "Pregunta al cliente que repuestos quiere comprar."
        )

    inventory = get_inventory()
    faltantes = []
    items = []
    for code in codigos:
        item = find_by_code(inventory, str(code))
        if item is None:
            faltantes.append(str(code))
        else:
            items.append(item)
    if faltantes:
        validos = ", ".join(i["codigo"] for i in inventory)
        return (
            f"No registre la venta: el codigo {', '.join(faltantes)} no existe en el "
            f"inventario. Codigos validos: {validos}."
        )

    if cantidades is None:
        cantidades = [1] * len(items)
    elif len(cantidades) != len(items):
        return (
            "No registre la venta: la lista de cantidades debe tener un valor por cada "
            f"codigo ({len(items)} codigos, {len(cantidades)} cantidades). "
            "Vuelve a llamar la herramienta con las cantidades alineadas."
        )

    shortages = []
    for item, cantidad in zip(items, cantidades):
        cantidad = int(cantidad)
        if cantidad < 1:
            shortages.append(f"{item['codigo']}: cantidad invalida ({cantidad})")
            continue
        if int(item["stock"]) < cantidad:
            shortages.append(
                f"{item['codigo']}: hay {item['stock']} y se pidieron {cantidad}"
            )
    if shortages:
        return (
            "No registre la venta por falta de stock:\n- "
            + "\n- ".join(shortages)
            + "\nInforma al cliente del stock real y no confirmes la venta."
        )

    try:
        from tools.db import registrar_venta as _registrar

        venta = _registrar(
            [
                {
                    "codigo": item["codigo"],
                    "cantidad": int(cantidad),
                    "precio_unitario": int(item["precio"]),
                }
                for item, cantidad in zip(items, cantidades)
            ],
            cliente=cliente,
            email=email_cliente,
            vehiculo=vehiculo,
            medio="agente",
        )
    except Exception as exc:
        return (
            f"No pude registrar la venta en la base de datos ({exc.__class__.__name__}: "
            f"{exc}). No confirmes la venta al cliente."
        )

    try:
        from tools.db import stock_por_codigo
        from tools.inventory_lookup import sincronizar_stock_csv

        sincronizar_stock_csv(stock_por_codigo())
    except Exception:
        pass
    reload_inventory()

    detalle_stock = "\n".join(
        f"- {d['codigo']}: stock {d['stock_antes']} -> {d['stock_despues']} "
        f"({d['cantidad']} unidad/es)"
        for d in venta["items"]
    )
    total = formatear_precio(venta["total"])
    mensaje = (
        f"Venta {venta['referencia']} REGISTRADA: {len(venta['items'])} item(s) por "
        f"${total}.\n{detalle_stock}\nStock actualizado en la base de datos interna."
    )

    if enviar_comprobante and email_cliente:
        ok, motivo = validar_email(email_cliente)
        if not ok:
            return f"{mensaje} No envie el comprobante: {motivo}."
        documento = {
            "tipo": "comprobante",
            "referencia": venta["referencia"],
            "fecha": venta["fecha"],
            "cliente": venta["cliente"] or "no indicado",
            "vehiculo": venta["vehiculo"] or "no indicado",
            "items": [
                {
                    "codigo": d["codigo"],
                    "descripcion": d["descripcion"],
                    "precio": d["precio_unitario"],
                    "stock": d["stock_despues"],
                    "stock_status": estado_stock(d["stock_despues"]),
                    "cantidad": d["cantidad"],
                }
                for d in venta["items"]
            ],
            "total": venta["total"],
            "avisos": [
                f"stock bajo: {d['codigo']}"
                for d in venta["items"]
                if int(d["stock_despues"]) < 5
            ],
        }
        path = _guardar_cotizacion(documento)
        resultado = enviar_cotizacion_documento(
            documento,
            email_cliente.strip(),
            vehiculo=vehiculo,
            mensaje=f"Comprobante de la venta {venta['referencia']}.",
            adjunto=path.read_bytes(),
            nombre_adjunto=path.name,
        )
        if resultado["enviado"]:
            return f"{mensaje}\nComprobante ENVIADO a {email_cliente.strip()}."
        if resultado["ruta"]:
            return (
                f"{mensaje}\nComprobante PREPARADO, NO se envio ({resultado['detalle']}). "
                "Informa al cliente que quedo listo y pendiente de envio."
            )
        return (
            f"{mensaje}\nNo pude enviar el comprobante: {resultado['detalle']} "
            f"Quedo guardado en {path}."
        )

    return mensaje


# --------------------------------------------------------------------------
# Recomendacion: RAG interno + manual + compatibilidad, con cita de fuente
# --------------------------------------------------------------------------
def _manual_hits(consulta: str, k: int = 2) -> tuple[list[dict], str]:
    """Busca en los manuales y devuelve (hits, aviso_de_error)."""
    try:
        from agent.rag import COL_MANUALS, ensure_index, search

        ensure_index()
        return search(COL_MANUALS, consulta, k=k), ""
    except Exception as exc:
        return [], f"{exc.__class__.__name__}: {exc}"


@tool
def recomendar_repuesto(marca: str, modelo: str, anio: str, tipo_repuesto: str = "") -> str:
    """Recomienda el repuesto correcto para un vehiculo (RAG interno + manual + compatibilidad).

    Usala cuando el cliente pida una recomendacion ("que repuesto me recomiendas
    para...", "que me conviene para..."). Cruza las tres fuentes del encargo:
    el inventario (precio y stock REAL), la compatibilidad registrada para el
    vehiculo y las especificaciones de los manuales tecnicos, y devuelve el
    codigo recomendado con la cita de la fuente.

    Si no hay respaldo en el inventario ni en los manuales, lo dice: nunca
    improvisa una recomendacion. Si el stock es bajo o esta agotado, avisa.
    """
    if not (marca or "").strip() or not (modelo or "").strip() or not (anio or "").strip():
        return (
            "No puedo recomendar un repuesto sin los tres datos del vehiculo. "
            "Pide marca, modelo y anio (ej: 'Suzuki Swift 2015') y vuelve a llamar "
            "esta herramienta."
        )

    inventory = get_inventory()
    vehiculo = f"{marca.strip()} {modelo.strip()} {anio.strip()}"
    resultados = search_parts(inventory, marca, modelo, anio, tipo=tipo_repuesto)

    aproximados = []
    if tipo_repuesto and resultados:
        exactos = [p for p in resultados if coincide_tipo(p, tipo_repuesto)]
        if exactos:
            resultados = exactos
        else:
            aproximados = resultados
            resultados = []

    if not resultados:
        if aproximados:
            lineas = "\n".join(f"- {format_part(p)}" for p in aproximados)
            codigos = ", ".join(p["codigo"] for p in aproximados)
            return (
                f"No hay '{tipo_repuesto}' exacto para {vehiculo}. La coincidencia mas "
                f"cercana en el inventario es:\n{lineas}\n"
                f"Aviso al cliente que {codigos} NO es exactamente el tipo que pidio."
            )
        genericos = search_parts(inventory, marca, modelo, anio)
        if genericos:
            lineas = "\n".join(f"- {format_part(p)}" for p in genericos)
            return (
                f"No hay repuestos de tipo '{tipo_repuesto}' para {vehiculo}. "
                f"Estos si existen para ese vehiculo:\n{lineas}"
            )
        return (
            diagnose_missing(inventory, marca, modelo, anio)
            + " No tengo informacion suficiente en el inventario ni en los manuales, "
            "asi que no te puedo recomendar un repuesto."
        )

    candidatos = []
    for item in resultados:
        cruce = compatibilidad_vehiculo(item, vehiculo)
        if cruce["coincide"]:
            candidatos.append((item, cruce))
    if not candidatos:
        lineas = "\n".join(f"- {format_part(p)}" for p in resultados)
        return (
            f"Hay repuestos en el inventario para {vehiculo}, pero ninguno tiene "
            f"registrada la compatibilidad con ese vehiculo:\n{lineas}\n"
            "No tengo informacion suficiente para recomendarte uno: no te puedo "
            "vender una pieza que no sea compatible."
        )

    mejor, cruce = candidatos[0]
    hits, error_manual = _manual_hits(
        f"{mejor['descripcion']} {marca} {modelo} especificaciones tecnicas", k=2
    )

    lineas = [
        f"RECOMENDACION: [{mejor['codigo']}] {mejor['descripcion']}",
        f"- Precio: ${formatear_precio(mejor['precio'])} | "
        f"Stock: {mejor['stock']} unidad/es",
        f"- Vehiculo: {vehiculo} -> compatible "
        f"(registrado: {mejor['vehiculos_compatibles']})",
    ]
    if mejor["stock"] == "0" or int(mejor["stock"]) <= 0:
        lineas.append("- ALERTA DE STOCK: este repuesto esta AGOTADO")
    elif int(mejor["stock"]) < 5:
        lineas.append(
            f"- ALERTA DE STOCK: quedan solo {mejor['stock']} unidades (stock bajo)"
        )

    if hits:
        primero = hits[0]
        meta = primero["metadatos"]
        fragmento = " ".join(primero["documento"].split())
        if len(fragmento) > 600:
            fragmento = fragmento[:600] + "..."
        lineas.append(
            f"- Especificacion tecnica (fuente: {meta.get('source')}, "
            f"pagina {meta.get('page')}): {fragmento}"
        )
    else:
        aviso = f" (no pude consultar los manuales: {error_manual})" if error_manual else ""
        lineas.append(
            "- Especificacion tecnica: no hay fragmento de los manuales para esta pieza"
            + aviso
        )

    alternativas = [p for p in resultados if p["codigo"] != mejor["codigo"]]
    if alternativas:
        detalle = "; ".join(
            f"[{p['codigo']}] {p['descripcion']} ${formatear_precio(p['precio'])} "
            f"(stock {p['stock']})"
            for p in alternativas[:3]
        )
        lineas.append(f"- Alternativas en inventario: {detalle}")
    if aproximados:
        codigos = ", ".join(p["codigo"] for p in aproximados)
        lineas.append(
            f"- Aviso: no hay '{tipo_repuesto}' exacto; {codigos} solo coincide "
            "parcialmente con ese tipo."
        )
    return "\n".join(lineas)


ALL_TOOLS = [
    buscar_repuesto,
    buscar_en_manual,
    verificar_compatibilidad,
    recordar_dato,
    recuperar_memoria,
    exportar_cotizacion,
    enviar_cotizacion_email,
    registrar_venta,
    recomendar_repuesto,
]
