# AVANCES — EvaluacionIA1 (Fase 0)

**Proyecto:** Asistente de IA para Venta de Repuestos Automotrices (RAG)
**Equipo:** Fabián Reyes Matías Vargas — Caso: Repuestos Sur
**Última actualización:** 2026-10-06

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
- [ ] Recrear `.env` desde `.env.example` (`.env` está gitignored y no está
      presente en este checkout) y pegar la `GROQ_API_KEY` real (o
      `OPENAI_API_KEY`).
- [x] Alinear `scripts/verify_env.py` con Groq: ahora valida el LLM según
      `LLM_PROVIDER` (Groq o OpenAI) y la verificación corre de punta a punta
      (Groq OK, embeddings 384d, ChromaDB OK).
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
- `.env` no está presente en este checkout (gitignored), aunque la actualización
  de 2026-09-09 registra su creación con key de Groq; debe recrearse localmente.
- `scripts/verify_env.py` validaba antes solo `OPENAI_API_KEY`; desde el
  2026-09-09 valida el proveedor activo (`LLM_PROVIDER`), incluido Groq.

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

## Actualización 2026-09-09 — verify_env.py alineado con Groq (Fase 0 listo)
- `scripts/verify_env.py` ya no valida solo `OPENAI_API_KEY`: lee `LLM_PROVIDER`
  y valida el proveedor activo (Groq usa `GROQ_API_KEY` + base_url de Groq;
  OpenAI igual que antes). Con `LLM_PROVIDER=groq`, el check del LLM aplica.
- Validado de punta a punta en este checkout:
  `uv run python scripts/verify_env.py` → Groq responde "OK", embeddings
  `dim=384`, ChromaDB recupera. También `uv run python main.py` (Suzuki Swift
  2015 → 4 repuestos con precio/stock; Toyota Corolla 2018 → sin repuestos).
- `.env` recreado localmente con `GROQ_API_KEY` (gitignored; no viaja en git).

## Actualización 2026-10-06 — Evaluación 2: agente, memoria, interfaz y evals

### Entorno
- Se creó `.venv` con Python 3.13 e instalaron con `pip` (uv no estaba
  disponible en esta máquina): `langchain 1.4.3`, `langchain-openai`,
  `chromadb 1.5.9`, `sentence-transformers 6.1`, `pypdf`, `python-dotenv`.
  Dependencias congeladas en `requirements.txt` (132 paquetes).
- `pyproject.toml` actualizado a lo realmente usado (se quitaron `pandas` y
  `langchain-community` que no se importaban; se agregaron `langchain-openai`
  y `pypdf`).

### ⚠️ Hallazgo: el modelo configurado ya no existía
- `groq/compound-mini` respondía **404 "model does not exist"**. Se listaron
  los modelos de la cuenta y se probaron con `tool_choice="required"`:
  - `qwen/qwen3.8-27b` ✅ y `openai/gpt-oss-20b` ✅ emitían tool_calls.
  - `openai/gpt-oss-120b` ❌ no llamó tools; `allam-2-7b` ❌ "tool calling is
    not supported".
- Se eligió **`qwen/qwen3.8-27b`** (elegía la tool correcta con argumentos
  precisos en la comparación de 4 escenarios). Cambio aplicado en `.env` y
  `.env.example`. `verify_env.py` ahora lo valida en cada corrida.

### Fase 1 — Ingesta RAG (completada)
- `agent/rag.py`: PDF → `RecursiveCharacterTextSplitter` 500/50 → embeddings
  locales → ChromaDB en `chroma_db/`. Colecciones `manuales` (3 fragmentos) e
  `inventario` (12 filas, completas por fila).
- `ingestion/ingest.py` (`--force`, `--stats`).

### Fases 2–4 — Agente, memoria y guardrails (completadas)
- `agent/agent.py`: `create_agent` de LangChain con 6 tools; loop
  plan → tool → observación → respuesta, con traza de pasos.
- `agent/tools.py`: `buscar_repuesto`, `buscar_en_manual`,
  `verificar_compatibilidad` (consulta) / `recordar_dato`,
  `exportar_cotizacion` (escritura) / `recuperar_memoria` (lectura).
- `agent/memory.py`: corto plazo (ventana de 10 turnos por sesión) y largo
  plazo (`data/memory/memoria.jsonl` + colección Chroma, recuperación
  semántica).
- `agent/guardrails.py` (post-LLM): códigos inexistentes → `no verificado` +
  aviso; stock <5 o agotado sin alerta → alerta agregada. Ignora los listados
  de catálogo (3+ códigos en la misma línea) para no generar falsos positivos.
- `agent/trace.py`: `logs/trace.jsonl` con entrada, plan, salida, tokens y
  guardrails.
- `main.py` refactorizado para importar `tools/inventory_lookup.py`,
  `agent/llm_client.py` y `agent/prompts.py` (sin duplicar lógica); la CLI
  sigue funcionando igual.

### Fase 6 — Interfaz web (completada)
- `web/server.py` (`http.server`, sin frameworks) + `web/static/index.html`
  (un solo archivo): búsqueda rápida marca/modelo/año, chat multi-turno con
  historial, tabla del inventario con alertas de stock y barra de estado del
  LLM. API: `GET /api/health`, `GET /api/inventory`, `POST /api/chat`,
  `POST /api/reset`.

### Fase 5 — Evals y evidencia (completada)
- `tests/eval_dataset.json`: 15 casos con criterios automáticos y
  justificación; `tests/eval_agent.py` genera
  `tests/resultados/eval_reporte.{md,json}`.
- **Resultado: 15/15 (100 %)** con meta ≥85 % (~46 500 tokens).
- Dos iteraciones de corrección que dejaron arreglo real:
  1. La memoria de largo plazo "contaminaba" los tests (el agente ya sabía el
     vehículo, así que no lo pedía ni lo volvía a guardar) → los tests ahora
     usan memoria aislada (`MEMORIA_FILE` / `MEMORIA_COLLECTION`).
  2. El agente **decía haber guardado un dato sin llamar `recordar_dato`** y
     pedía el vehículo para consultas de manual → se reforzó el system prompt
     (reglas 5 y 8) y se bajó la temperatura del loop a 0.1.

### Docs
- `README.md` reescrito con instrucciones precisas de ejecución, estructura,
  herramientas, reglas de seguridad, configuración, resultados de pruebas y
  referencias APA.
- `.gitignore`: ahora ignora `data/exports/` y `data/memory/*.jsonl`.