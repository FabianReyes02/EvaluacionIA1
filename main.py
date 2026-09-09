"""Asistente basico de repuestos automotrices.
Pregunta marca, modelo y anio del auto, busca en el inventario CSV
y muestra los repuestos disponibles con stock y precio.
"""

import csv
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
        year_int = int(year)
    except ValueError:
        return []
    results = []
    for item in inventory:
        compat = item["vehiculos_compatibles"].lower()
        if brand.lower() in compat and model.lower() in compat and year_matches(compat, year_int):
            results.append(item)
    return results


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
        "Si no hay repuestos, indica que no se encontraron."
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


def format_plain(parts: list[dict], brand: str, model: str, year: str) -> str:
    """Fallback sin IA: muestra los repuestos en texto plano."""
    if not parts:
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
        print("Modelo LLM: no se uso (sin repuestos encontrados o sin API key)")
        print("Temperatura: %.1f (definida, no aplicada)" % TEMPERATURE)
    print(f"Archivo fuente de datos: {os.path.abspath(INVENTORY_PATH)}")


def main():
    print("=== Asistente de Repuestos Automotrices ===")
    print("Te ayudo a encontrar repuestos compatibles con tu auto.\n")

    brand = input("Marca del auto (ej: Suzuki, Hyundai, Chevrolet): ").strip()
    model = input("Modelo del auto (ej: Swift, Accent, Sail): ").strip()
    year = input("Anio del auto (ej: 2015): ").strip()

    if not all([brand, model, year]):
        print("Debes ingresar marca, modelo y anio.")
        return

    print(f"\nBuscando repuestos para {brand} {model} {year} en el inventario...")
    inventory = load_inventory(INVENTORY_PATH)
    results = search_parts(inventory, brand, model, year)
    print(f"Candidatos compatibles encontrados: {len(results)}")

    client, llm_model = get_client_and_model()
    tokens = None
    used_llm = False

    if results:
        if client is None:
            answer = format_plain(results, brand, model, year)
        else:
            print(f"Generando respuesta con {llm_model}...\n")
            prompt = build_prompt(results, brand, model, year)
            answer, tokens = ask_llm(client, llm_model, prompt)
            used_llm = True
            if answer is None:
                print("Usando respuesta sin IA como alternativa.\n")
                answer = format_plain(results, brand, model, year)
    else:
        answer = format_plain(results, brand, model, year)

    print("\n--- Resultado ---\n")
    print(answer)
    print_metadata(llm_model, tokens, used_llm)


if __name__ == "__main__":
    main()