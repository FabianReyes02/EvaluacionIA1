# 🚗 Asistente de IA para Venta de Repuestos Automotrices (RAG)

**ISY0101 · Ingeniería de Soluciones con IA · Evaluación Parcial 1 (30%)**

## 📌 Descripción del Proyecto
Este proyecto es una solución integral basada en Inteligencia Artificial (LLMs) y pipelines RAG (Recuperación Aumentada de Generación). Su objetivo es asistir a vendedores y clientes en la identificación precisa de repuestos automotrices, cruzando información de manuales técnicos (PDF) con el inventario interno de la tienda (CSV).

> **Estado:** MVP básico (`main.py`) funcionando: cruza el inventario CSV con
> un LLM intercambiable (Groq/OpenAI). El RAG completo (manuales PDF +
> ChromaDB) y las evals están pendientes (Fases 1–5). Decisiones técnicas y
> avance del semestre en [`agents.md`](agents.md).

## 👥 Equipo de Trabajo
* **Estudiantes:** Fabián Reyes y Matías Vargas
* **Caso Organizacional:** Repuestos Sur

## 🛠️ Tecnologías Utilizadas
* **Lenguaje:** Python 3.11+ (uv como gestor de dependencias)
* **Orquestador:** LangChain (LlamaIndex como alternativa documentada)
* **Base de Datos Vectorial:** ChromaDB (FAISS como alternativa documentada)
* **LLM:** OpenAI o Groq, intercambiable vía `LLM_PROVIDER` (default: Groq
  `groq/compound-mini`; Anthropic documentado como alternativa, aún no implementado)

## ⚙️ Requisitos Previos (Prerrequisitos)
Antes de ejecutar este proyecto, asegúrate de tener instalado:
* Python 3.11 o superior.
* `uv` (gestor de dependencias): https://docs.astral.sh/uv/
* Una clave de API para el LLM (ej. `GROQ_API_KEY` o `OPENAI_API_KEY`).

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
   cp .env.example .env   # pegar GROQ_API_KEY o OPENAI_API_KEY
   ```

4. **Generar datos de ejemplo (inventario CSV + manuales PDF):**
   ```bash
   uv run python scripts/generate_sample_data.py
   ```

5. **Verificar el entorno (LLM, embeddings, ChromaDB):**
   ```bash
   uv run python scripts/verify_env.py
   ```
   (Nota: `verify_env.py` valida datos, embeddings y ChromaDB; el check del LLM
   usa `OPENAI_API_KEY` por ahora.)

6. **Usar el asistente (MVP):**
   ```bash
   uv run python main.py
   ```

Documentación completa (arquitectura, fuentes internas/externas, evaluación,
limitaciones) se completa en la Fase 6 del plan.