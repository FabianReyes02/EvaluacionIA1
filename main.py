"""CLI interactiva del asistente de repuestos (modo consola).

Usa los mismos modulos que el agente y la interfaz web:
  tools/inventory_lookup.py  busqueda y diagnostico sobre el CSV
  agent/llm_client.py        cliente LLM intercambiable
  agent/prompts.py           prompts de validacion y presentacion
"""
import json
import os
import re
import sys

from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()

from agent.llm_client import add_tokens, ask_llm, get_chat_model, get_provider_config
from agent.prompts import build_not_found_prompt, build_prompt, build_validation_prompt
from tools.inventory_lookup import (
    INVENTORY_PATH,
    diagnose_missing,
    format_plain,
    get_catalog_summary,
    load_inventory,
    search_parts,
)


def validate_with_llm(model, raw_brand: str, raw_model: str, raw_year: str, catalog: str):
    """Llamada 1: el modelo normaliza y verifica los datos. Devuelve (dict, tokens)."""
    prompt = build_validation_prompt(raw_brand, raw_model, raw_year, catalog)
    answer, tokens = ask_llm(prompt, model)
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


def print_metadata(model: str | None, tokens: dict | None, used_llm: bool):
    print("\n--- Detalles de la consulta ---")
    if used_llm and model:
        print(f"Modelo LLM: {model}")
        print("Temperatura: %.1f" % 0.3)
        if tokens:
            print(
                f"Tokens usados: {tokens['prompt']} de entrada | "
                f"{tokens['completion']} de salida | {tokens['total']} totales"
            )
    else:
        print("Modelo LLM: no se uso (sin API key o fallo la llamada)")
        print("Temperatura: %.1f (definida, no aplicada)" % 0.3)
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

    model = get_chat_model()
    cfg = get_provider_config()
    llm_model = cfg["model"] if cfg else None
    tokens = None
    used_llm = False

    # Sin LLM: busqueda directa + diagnostico especifico (marca/modelo/anio).
    if model is None:
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
    validation, val_tokens = validate_with_llm(model, raw_brand, raw_model, raw_year, catalog)
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

    if validation["necesita_aclaracion"] or not all(
        [validation["marca"], validation["modelo"], validation["anio"]]
    ):
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
        answer, ans_tokens = ask_llm(build_prompt(results, brand, model_car, year), model)
        tokens = add_tokens(tokens, ans_tokens)
        if answer is None:
            print("Usando respuesta sin IA como alternativa.\n")
            answer = format_plain(results, brand, model_car, year, inventory)
    else:
        # Verificado en codigo: no hay stock para esos datos -> el modelo lo explica
        # mencionando si es la marca, el modelo o el anio.
        detail = diagnose_missing(inventory, brand, model_car, year)
        print(f"Generando respuesta con {llm_model}...\n")
        answer, ans_tokens = ask_llm(
            build_not_found_prompt(brand, model_car, year, detail), model
        )
        tokens = add_tokens(tokens, ans_tokens)
        if answer is None:
            print("Usando respuesta sin IA como alternativa.\n")
            answer = detail

    print("\n--- Resultado ---\n")
    print(answer)
    print_metadata(llm_model, tokens, used_llm)


if __name__ == "__main__":
    main()
