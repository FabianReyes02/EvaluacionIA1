# AVANCES — EvaluacionIA1 (Fase 0)

**Proyecto:** Asistente de IA para Venta de Repuestos Automotrices (RAG)
**Equipo:** Fabián Reyes Matías Vargas — Caso: Repuestos Sur
**Última actualización:** 2026-09-08

## Lo que se hizo

### 1. Análisis y planificación
- Se analizó la estructura del proyecto de referencia `ep1-veterinaria-agente`
  (misma asignatura ISY0101, EP1) como plantilla de arquitectura.
- Se adaptó el stack al README original del proyecto: LangChain como
  orquestador, ChromaDB como vector store, OpenAI como LLM (con Anthropic
  intercambiable), manejo de dependencias con uv.

### 2. Fase 0 — Scaffold (completada)
Estructura creada en el repositorio:

```
EvaluacionIA1/
├── agent/__init__.py              # Paquete: orquestación LLM, prompts, RAG, trazabilidad
├── tools/__init__.py              # Paquete: buscador de repuestos y validador de compatibilidad
├── ingestion/__init__.py          # Paquete: ingesta PDF + CSV, chunking e índice
├── scripts/
│   ├── verify_env.py              # Verifica OpenAI, embeddings locales, ChromaDB y datos
│   └── generate_sample_data.py    # Genera inventory.csv + manuales PDF de ejemplo
├── data/
│   ├── internal/inventory.csv     # 12 repuestos de ejemplo (código, marca, precio, stock…)
│   └── external/manuales/         # 2 manuales técnicos PDF (alternador y kit embrague)
├── .env.example                   # OPENAI_API_KEY, LLM_PROVIDER, OPENAI_MODEL, EMBEDDING_MODEL
├── .gitignore                     # .env, .venv, chroma_db/, logs/, caches
├── .python-version                # 3.11
├── pyproject.toml                 # Dependencias del proyecto (uv)
├── uv.lock                        # Bloqueo de dependencias generado por uv
├── agents.md                      # Memoria de decisiones (D1-D7) y plan de fases
└── README.md                      # Actualizado: instalación, config y comandos
```

### 3. Configuración y validación
- `uv sync`: 157 paquetes resueltos, 132 instalados (langchain 1.4, chromadb
  1.5, openai 3.9, sentence-transformers 6.0, fpdf2 2.8…), entorno `.venv`
  creado con Python 3.11.
- `uv run python scripts/generate_sample_data.py`: generó el inventario CSV
  (12 repuestos) y 2 manuales PDF. Se corrigió un problema de codificación de
  consola Windows (cp1252) reconfigurando stdout a UTF-8.
- `uv run python scripts/verify_env.py`: detecta correctamente los datos y el
  estado de `OPENAI_API_KEY`. La verificación completa (LLM + embeddings +
  ChromaDB) queda pendiente de la key.

### 4. Git
- Commit `d60488e` "Fase 0: scaffold del agente RAG de repuestos automotrices"
  (15 archivos) y push a `origin/main`.
- Se configuró el credential helper de Git (Git Credential Manager) para
  autenticación con GitHub.

## Lo que queda pendiente

### Inmediato (antes de la Fase 1)
- [ ] Copiar `.env.example` a `.env` y pegar la `OPENAI_API_KEY` real.
- [ ] `uv run python scripts/verify_env.py` para validar de punta a punta
      LLM, embeddings y ChromaDB (la primera ejecución descarga ~470MB del
      modelo de embeddings).

### Fases del plan (según agents.md)
- [ ] **Fase 1** — Ingesta real: cargar CSV y PDF (document loaders de
      LangChain), chunking (`RecursiveCharacterTextSplitter` 500/50) e índice
      ChromaDB persistente en `chroma_db/`.
- [ ] **Fase 2** — `agent/llm_client.py` (LLM intercambiable), `prompts.py` y
      chain RAG base con citas de fuente.
- [ ] **Fase 3** — `tools/inventory_lookup.py` (búsqueda en inventario) y
      `tools/compatibility_checker.py` (validación vehículo/modelo), `main.py`
      CLI y `agent/trace.py` (log JSONL de trazabilidad).
- [ ] **Fase 4** — Guardrails de seguridad en código (post-LLM): nunca sugerir
      un repuesto sin fuente; alerta explícita por stock crítico.
- [ ] **Fase 5** — Evals: `tests/eval_dataset.json` (12-15 casos, meta ≥85%) y
      `tests/eval_agent.py`.
- [ ] **Fase 6** — README completo + diagrama Mermaid + `docs/` (informe).

## Notas / limitaciones
- Los manuales técnicos y el inventario actuales son **datos de ejemplo
  simulados** (no son los datos reales de Repuestos Sur).
- La primera ejecución del modelo de embeddings descarga ~470MB (una sola vez).

## Actualización 2026-09-09 — MVP básico (main.py)
- Se creó `.env` con la key de **Groq** (gratis; `LLM_PROVIDER=groq`,
  `GROQ_MODEL=groq/compound-mini`). Se verificó el modelo contra la API de
  Groq, ya que `llama-3.3-70b-versatile` no está disponible en esta cuenta.
- Se agregó `main.py`: flujo básico por consola que pregunta **marca, modelo y
  anio**, busca en `data/internal/inventory.csv` (interpreta rangos de anios
  tipo "2014-2019" con regex) y responde con repuestos, precio, stock y
  alerta si el stock es bajo.
- El cliente LLM es intercambiable vía `LLM_PROVIDER` (OpenAI o Groq, con la
  API de OpenAI). Si la llamada al LLM falla, cae a respuesta en texto plano.
- Si no hay repuestos para el vehículo, responde directamente sin llamar al
  LLM ("No se encontraron repuestos…") para evitar consultas innecesarias.
- Se corrigió el encoding de consola Windows (stdout a UTF-8) porque el LLM
  devuelve caracteres que cp1252 no puede imprimir.
- Probado: `Suzuki Swift 2015/2018` → 4 repuestos con precio y stock;
  `Toyota Corolla 2018` → mensaje de no encontrado.
- Comando de uso: `uv run python main.py`