import csv
import json
import os
import re
import sys
from dotenv import load_dotenv
from openai import OpenAI

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()

INVENTORY_PATH = os.path.join("data", "internal", "inventory.csv")
TEMPERATURE = 0.3

PROVIDERS = {
    "openai": {"base_url": None, "key_env": "OPENAI_API_KEY", "model_env": "OPENAI_MODEL"},
    "groq": {"base_url": "https://api.groq.com/openai/v1", "key_env": "GROQ_API_KEY", "model_env": "GROQ_MODEL"},
}


def get_client_and_model():
    provider = os.getenv("LLM_PROVIDER", "openai")
    if provider not in PROVIDERS:
        provider = "openai"
    cfg = PROVIDERS[provider]
    api_key = os.getenv(cfg["key_env"])
    model = os.getenv(cfg["model_env"])
    if not api_key or not model:
        return None, None
    if cfg["base_url"]:
        client = OpenAI(api_key=api_key, base_url=cfg["base_url"])
    else:
        client = OpenAI(api_key=api_key)
    return client, model


def load_inventory(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def year_matches(compat: str, year: int) -> bool:
    """True si el anio cae dentro de uno de los rangos en la cadena de compatibilidad."""
    for lo, hi in re.findall(r"(\d{4})\s*-\s*(\d{4})", compat):
        if int(lo) <= year <= int(hi):
            return True
    return False


def search_parts(inventory: list[dict], brand: str, model: str, year: str) -> list[dict]:
    """Busca repuestos cuyos vehiculos_compatibles contengan la marca, modelo y anio."""
    try:
        year_int = int(str(year).strip())
    except ValueError:
        return []
    if not brand or not model:
        return []
    results = []
    for item in inventory:
        compat = item["vehiculos_compatibles"].lower()
        if brand.lower() in compat and model.lower() in compat and year_matches(compat, year_int):
            results.append(item)
    return results


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
        faltantes.append("año")
    if faltantes:
        return (
            f"No hay repuestos para mostrar porque falta ingresar: {', '.join(faltantes)}. "
            f"Por favor indica marca, modelo y año (ej: Suzuki Swift 2015)."
        )

    try:
        year_int = int(year)
        anio_valido = 1900 <= year_int <= 2030
    except ValueError:
        return (
            f"No hay repuestos para el año '{year}' porque no es un año válido. "
            f"Ingresa el año con 4 dígitos (ej: 2015)."
        )
    if not anio_valido:
        return (
            f"No hay repuestos para el año '{year}' porque está fuera de rango. "
            f"Ingresa un año válido con 4 dígitos (ej: 2015)."
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
            f"La marca '{brand}' sí tiene repuestos, pero no para ese modelo. "
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
        f"No hay repuestos para el año '{year}' del {brand} {model} en el inventario. "
        f"Compatibilidades registradas para ese modelo: {rangos_txt}."
    )


def build_prompt(parts: list[dict], brand: str, model: str, year: str) -> str:
    inventory_text = ""
    for p in parts:
        inventory_text += (
            f"- Codigo: {p['codigo']} | Descripcion: {p['descripcion']} | "
            f"Marca: {p['marca']} | Precio: ${p['precio']} | Stock: {p['stock']} unidades\n"
        )
    return (
        f"Un cliente busca repuestos para un {brand} {model} {year}.\n"
        f"Estos son los repuestos disponibles en inventario:\n{inventory_text}\n"
        "Responde en espanol, de forma breve y clara. "
        "Muestra cada repuesto con su codigo, descripcion, precio y stock. "
        "Si el stock es bajo (menos de 5), adviertelo. "
        "Si el cliente no ingreso marca, modelo o anio, indicalo y no muestres repuestos., o pregunta algo fuera de contexto indicalo"
    )


def build_validation_prompt(raw_brand: str, raw_model: str, raw_year: str, catalog: str) -> str:
    return (
        'Eres el validador de datos de la tienda "Repuestos Sur".\n'
        "Catalogo real de vehiculos con repuestos (unica fuente valida):\n"
        f"{catalog}\n\n"
        "Datos ingresados por el cliente:\n"
        f'- Marca: "{raw_brand}" | Modelo: "{raw_model}" | Anio: "{raw_year}"\n\n'
        "Tarea: corrige errores de tipeo (ej. susuki->Suzuki, swif->Swift, acent->Accent, "
        'sail->Sail, rio->Rio 4), normaliza el anio a 4 digitos YYYY (ej. "15"->"2015" solo '
        'si es evidente entre 1990-2030, "dos mil quince"->"2015") y verifica contra el catalogo.\n'
        "Reglas:\n"
        "- No inventes marcas, modelos ni anios fuera del catalogo. "
        "Si no hay coincidencia razonable, marca necesita_aclaracion=true.\n"
        "- Si falta algun dato o el anio no es un anio valido, marca necesita_aclaracion=true.\n"
        "- Responde SOLO con JSON valido, sin markdown ni texto extra, con esta forma exacta:\n"
        '{"marca_normalizada": "..."|null, "modelo_normalizado": "..."|null, '
        '"anio_normalizado": "..."|null, "confianza": "alta|media|baja", '
        '"necesita_aclaracion": true|false, "mensaje_usuario": "..."}\n'
        '- mensaje_usuario: en espanol, breve. Si todo OK confirma ej. '
        '"Datos validados: Suzuki Swift 2015." Si hay problema, explica que dato '
        "esta mal o falta (marca, modelo o anio segun sea el caso) y pide corregirlo."
    )


def build_not_found_prompt(brand: str, model: str, year: str, detail: str) -> str:
    return (
        f"El cliente busca repuestos para {brand} {model} {year}.\n"
        f"Verificacion en inventario: {detail}\n\n"
        "Redacta en espanol, de forma breve y amable, un mensaje que explique que no hay "
        "repuestos para ese caso especifico. Menciona de forma explicita si el problema es "
        "la marca, el modelo o el anio, segun el detalle de la verificacion. "
        "No inventes repuestos, codigos ni alternativas. "
        "Si el detalle incluye rangos o compatibilidades registradas, mencionalos."
    )


def ask_llm(client, model: str, prompt: str):
    """Devuelve (respuesta, dict de uso de tokens) o (None, None) si falla."""
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=TEMPERATURE,
        )
        usage = resp.usage
        tokens = {
            "prompt": usage.prompt_tokens,
            "completion": usage.completion_tokens,
            "total": usage.total_tokens,
        }
        return resp.choices[0].message.content, tokens
    except Exception as exc:
        print(f"(aviso) La llamada al LLM fallo: {exc.__class__.__name__}")
        return None, None


def add_tokens(a: dict | None, b: dict | None) -> dict | None:
    if a is None:
        return b
    if b is None:
        return a
    return {
        "prompt": a["prompt"] + b["prompt"],
        "completion": a["completion"] + b["completion"],
        "total": a["total"] + b["total"],
    }


def validate_with_llm(client, model: str, raw_brand: str, raw_model: str, raw_year: str, catalog: str):
    """Llamada 1: el modelo normaliza y verifica los datos. Devuelve (dict, tokens)."""
    prompt = build_validation_prompt(raw_brand, raw_model, raw_year, catalog)
    answer, tokens = ask_llm(client, model, prompt)
    if answer is None:
        return None, tokens
    try:
        match = re.search(r"\{.*\}", answer, re.DOTALL)
        data = json.loads(match.group(0) if match else answer)
        return {
            "marca": (data.get("marca_normalizada") or "").strip(),
            "modelo": (data.get("modelo_normalizado") or "").strip(),
            "anio": str(data.get("anio_normalizado") or "").strip(),
            "confianza": data.get("confianza", "baja"),
            "necesita_aclaracion": bool(data.get("necesita_aclaracion", True)),
            "mensaje": (data.get("mensaje_usuario") or "").strip(),
        }, tokens
    except Exception:
        print("(aviso) El validador no devolvio un JSON valido, usando busqueda directa.")
        return None, tokens


def format_plain(parts: list[dict], brand: str, model: str, year: str, inventory: list[dict] | None = None) -> str:
    """Fallback sin IA: muestra los repuestos en texto plano."""
    if not parts:
        if inventory is not None:
            return diagnose_missing(inventory, brand, model, year)
        return f"No se encontraron repuestos para {brand} {model} {year}."
    lines = [f"Repuestos para {brand} {model} {year}:"]
    for p in parts:
        stock_note = " (STOCK BAJO)" if int(p["stock"]) < 5 else ""
        lines.append(
            f"  [{p['codigo']}] {p['descripcion']} - ${p['precio']} - "
            f"Stock: {p['stock']}{stock_note}"
        )
    return "\n".join(lines)


def print_metadata(model: str, tokens: dict | None, used_llm: bool):
    print("\n--- Detalles de la consulta ---")
    if used_llm and model:
        print(f"Modelo LLM: {model}")
        print("Temperatura: %.1f" % TEMPERATURE)
        if tokens:
            print(
                f"Tokens usados: {tokens['prompt']} de entrada | "
                f"{tokens['completion']} de salida | {tokens['total']} totales"
            )
    else:
        print("Modelo LLM: no se uso (sin API key o fallo la llamada)")
        print("Temperatura: %.1f (definida, no aplicada)" % TEMPERATURE)
    print(f"Archivo fuente de datos: {os.path.abspath(INVENTORY_PATH)}")


def main():
    print("=== Asistente de Repuestos Automotrices ===")
    print("Te ayudo a encontrar repuestos compatibles con tu auto.\n")

    # Se leen tal cual: el modelo valida desde el inicio, sin if previos que lo bloqueen.
    raw_brand = input("Marca del auto (ej: Suzuki, Hyundai, Chevrolet): ").strip()
    raw_model = input("Modelo del auto (ej: Swift, Accent, Sail): ").strip()
    raw_year = input("Anio del auto (ej: 2015): ").strip()

    inventory = load_inventory(INVENTORY_PATH)
    catalog = get_catalog_summary(inventory)

    client, llm_model = get_client_and_model()
    tokens = None
    used_llm = False

    # Sin LLM: busqueda directa + diagnostico especifico (marca/modelo/anio).
    if client is None:
        results = search_parts(inventory, raw_brand, raw_model, raw_year)
        answer = (
            format_plain(results, raw_brand, raw_model, raw_year, inventory)
            if results
            else diagnose_missing(inventory, raw_brand, raw_model, raw_year)
        )
        print("\n--- Resultado ---\n")
        print(answer)
        print_metadata(llm_model, tokens, used_llm)
        return

    # Llamada 1: el modelo verifica y normaliza los datos desde el inicio.
    print(f"Validando datos con {llm_model}...\n")
    validation, val_tokens = validate_with_llm(client, llm_model, raw_brand, raw_model, raw_year, catalog)
    tokens = add_tokens(tokens, val_tokens)
    if validation is not None:
        used_llm = True

    if validation is None:
        # El validador fallo: busqueda directa con lo crudo + mensaje especifico.
        print("Usando busqueda directa como alternativa.\n")
        results = search_parts(inventory, raw_brand, raw_model, raw_year)
        print(f"Candidatos compatibles encontrados: {len(results)}")
        answer = (
            format_plain(results, raw_brand, raw_model, raw_year, inventory)
            if results
            else diagnose_missing(inventory, raw_brand, raw_model, raw_year)
        )
        print("\n--- Resultado ---\n")
        print(answer)
        print_metadata(llm_model, tokens, used_llm)
        return

    if validation["necesita_aclaracion"] or not all([validation["marca"], validation["modelo"], validation["anio"]]):
        # El modelo detecto datos malos/incompletos: lo dice el mismo + detalle de campo.
        detail = diagnose_missing(
            inventory,
            validation["marca"] or raw_brand,
            validation["modelo"] or raw_model,
            validation["anio"] or raw_year,
        )
        print("\n--- Resultado ---\n")
        print(validation["mensaje"] or detail)
        print(detail)
        print_metadata(llm_model, tokens, used_llm)
        return

    brand, model_car, year = validation["marca"], validation["modelo"], validation["anio"]
    print(f"Datos validados: {brand} {model_car} {year} (confianza: {validation['confianza']})")
    results = search_parts(inventory, brand, model_car, year)
    print(f"Candidatos compatibles encontrados: {len(results)}")

    if results:
        # Llamada 2: el modelo presenta los repuestos verificados en el CSV.
        print(f"Generando respuesta con {llm_model}...\n")
        prompt = build_prompt(results, brand, model_car, year)
        answer, ans_tokens = ask_llm(client, llm_model, prompt)
        tokens = add_tokens(tokens, ans_tokens)
        if answer is None:
            print("Usando respuesta sin IA como alternativa.\n")
            answer = format_plain(results, brand, model_car, year, inventory)
    else:
        # Verificado en codigo: no hay stock para esos datos -> el modelo lo explica
        # mencionando si es la marca, el modelo o el anio.
        detail = diagnose_missing(inventory, brand, model_car, year)
        print(f"Generando respuesta con {llm_model}...\n")
        answer, ans_tokens = ask_llm(client, llm_model, build_not_found_prompt(brand, model_car, year, detail))
        tokens = add_tokens(tokens, ans_tokens)
        if answer is None:
            print("Usando respuesta sin IA como alternativa.\n")
            answer = detail

    print("\n--- Resultado ---\n")
    print(answer)
    print_metadata(llm_model, tokens, used_llm)


if __name__ == "__main__":
    main()
