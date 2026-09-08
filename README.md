# 🚗 Asistente de IA para Venta de Repuestos Automotrices (RAG)

**ISY0101 · Ingeniería de Soluciones con IA · Evaluación Parcial 1 (30%)**

## 📌 Descripción del Proyecto
Este proyecto es una solución integral basada en Inteligencia Artificial (LLMs) y pipelines RAG (Recuperación Aumentada de Generación). Su objetivo es asistir a vendedores y clientes en la identificación precisa de repuestos automotrices, cruzando información de manuales técnicos (PDF) con el inventario interno de la tienda (CSV).

> **Estado:** Fase 0 (scaffold). Decisiones técnicas y avance del semestre en
> [`agents.md`](agents.md).

## 👥 Equipo de Trabajo
* **Estudiante** Fabián Reyes
* **Caso Organizacional:** Repuestos Sur

## 🛠️ Tecnologías Utilizadas
* **Lenguaje:** Python 3.11+ (uv como gestor de dependencias)
* **Orquestador:** LangChain (LlamaIndex como alternativa documentada)
* **Base de Datos Vectorial:** ChromaDB (FAISS como alternativa documentada)
* **LLM:** OpenAI API (Anthropic intercambiable vía `LLM_PROVIDER`)

## ⚙️ Requisitos Previos (Prerrequisitos)
Antes de ejecutar este proyecto, asegúrate de tener instalado:
* Python 3.11 o superior.
* `uv` (gestor de dependencias): https://docs.astral.sh/uv/
* Una clave de API válida para el LLM (ej. `OPENAI_API_KEY`).

## 🚀 Instrucciones de Instalación
Sigue estos pasos para configurar el entorno local:

1. **Clonar el repositorio:**
   ```bash
   git clone https://github.com/FabianReyes02/EvaluacionIA1.git
   cd EvaluacionIA1
   ```

2. **Sincronizar dependencias (crea `.venv`):**
   ```bash
   uv sync
   ```

3. **Configurar credenciales:**
   ```bash
   cp .env.example .env   # pegar OPENAI_API_KEY de https://platform.openai.com/api-keys
   ```

4. **Generar datos de ejemplo (inventario CSV + manuales PDF):**
   ```bash
   uv run python scripts/generate_sample_data.py
   ```

5. **Verificar el entorno (LLM, embeddings, ChromaDB):**
   ```bash
   uv run python scripts/verify_env.py
   ```

Documentación completa (arquitectura, fuentes internas/externas, evaluación,
limitaciones) se completa en la Fase 6 del plan.