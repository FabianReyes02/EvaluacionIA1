# agents.md — Memoria de decisiones y avance del semestre

**Proyecto:** EvaluacionIA1 (Asistente de IA para Venta de Repuestos Automotrices)
**Curso:** ISY0101 Ingeniería de Soluciones con IA — Evaluación Parcial 1 (30%)
**GitHub:** https://github.com/FabianReyes02/EvaluacionIA1
**Última actualización:** 2026-10-08

> Memoria técnica del proyecto. Se actualiza en cada sesión para preservar
> decisiones, tradeoffs y avance entre entregas. Sirve de bitácora para el
> docente (IE7/IE8: justificar decisiones) y para el equipo.

## 1. Contexto del semestre

- EP1 = 1 caso organizacional + informe de 5 páginas APA (IE1–IE9). Se
  desarrolla en parejas, 5 semanas.
- Caso organizacional: **Repuestos Sur** — tienda de repuestos automotrices
  que necesita asistir a vendedores/clientes para identificar repuestos
  correctos cruzando manuales técnicos (PDF) con el inventario interno (CSV).
- Regla del stack: **≥50% con tecnologías vistas en clase es concepto guía,
  no requisito literal.** El profesor alienta la exploración. Toda tecnología
  fuera del curso debe quedar justificada aquí y en el informe.

## 2. Decisiones cerradas

| # | Decisión | Elección | Justificación | Alternativa descartada |
|---|---|---|---|---|
| D1 | Proveedor LLM | OpenAI (`gpt-4o-mini`) o Groq (`groq/compound-mini`, gratis) intercambiable vía `LLM_PROVIDER` en `.env` (default actual: `groq`) | API OpenAI-compatible y ampliamente documentada; Groq sin costo para el prototipo. Anthropic documentado como alternativa, aún no implementado | Proveedor local sin API |
| D2 | Embeddings | `paraphrase-multilingual-MiniLM-L12-v2` local (384d) | Contenido en español; costo 0 y privado | `all-MiniLM-L6-v2` (enfoque inglés) |
| D3 | Vector store | **ChromaDB** persistente en `chroma_db/` sobre FAISS | Filtro nativo por metadata (`marca`, `categoria`, `tipo_fuente`); API simple. FAISS se documenta como alternativa del curso (RA1/IL1.3) | FAISS |
| D4 | Chunking | Manuales PDF con `RecursiveCharacterTextSplitter`-style 500/50 (visto en RA1/IL1.3); entradas de inventario (CSV) completas por fila | Fragmentos de manual deben recuperarse íntegros para mantener especificaciones coherentes (compatibilidad, medidas) | Chunk grande genérico |
| D5 | Gestor de deps | uv + Python 3.11 | Convención del curso (uv.lock en repo materiales) | pip |
| D6 | Orquestación | **LangChain** (chains RAG + document loaders de la comunidad) | README del proyecto lo indica; versiones y ecosistema maduros | LlamaIndex (documentado como alternativa) |
| D7 | Datos | Ejemplo generado por `scripts/generate_sample_data.py` (CSV inventario + PDF manuales técnicos) | Escasez de datos reales; replicable y versionable | Datos externos sin licenciar |
| D8 | Modelo LLM | Groq `qwen/qwen3.8-27b` (antes `groq/compound-mini`) | El anterior respondía 404; se probaron 4 modelos con `tool_choice="required"` y solo `qwen3.8-27b` y `gpt-oss-20b` emitían tool_calls. Qwen eligió la tool correcta con argumentos precisos en los 4 escenarios de prueba | `openai/gpt-oss-120b` (no llamó tools), `allam-2-7b` (sin soporte), `gpt-oss-20b` (respaldo documentado) |
| D9 | Memoria | Corto plazo: ventana de 10 turnos por sesión en memoria. Largo plazo: `data/memory/memoria.jsonl` **+** colección Chroma con recuperación semántica, escrita/leída por tools que el agente decide llamar | Cumple "corto y largo plazo" con una sola tecnología ya presente; el JSONL garantiza persistencia aunque Chroma falle | Solo `ConversationBuffer` (sin persistencia) o base vectorial dedicada |
| D10 | Guardrails | Verificación **post-LLM** en `agent/guardrails.py`: todo código mencionado se contrasta con el CSV y todo stock crítico exige alerta | La regla es no negociable y un prompt no garantiza el comportamiento (el agente llegó a decir que guardó un dato sin llamar la tool) | Confiar solo en el system prompt |
| D11 | Entorno | `pip` + `.venv` (Python 3.13) con `requirements.txt` congelado | `uv` no estaba disponible en la máquina de desarrollo; se priorizó poder ejecutar y evaluar el agente | Instalar uv y regenerar `uv.lock` (pendiente si se retoma D5) |
| D12 | Resiliencia 429 | Reintentos con backoff **solo ante límite de tasa** en `agent/agent.py` + `agent/llm_client.py` (3 intentos, 20s/40s/60s, env `AGENT_RETRY_ATTEMPTS`/`AGENT_RETRY_BASE_S`); mensaje amable + fallback CSV si se agotan | El plan gratuito Groq limita a 1000 OTPM y los evals lo disparan; reintentar todo duplicaría llamadas pagadas | Reintentar errores genéricos o solo confiar en el fallback seco |

Convencion de commits: mensajes simples y en espanol durante todo el semestre.

## 3. Requisitos funcionales (encargo)

Tienda de repuestos pequeños («Repuestos Sur») necesita que vendedores y
clientes identifiquen el repuesto correcto sin depender del conocimiento de un
especialista. Dada una consulta (ej. «alternador para Suzuki Swift 2014»):

1. RAG externo: recuperar la especificación técnica del repuesto desde los
   manuales técnicos (PDF).
2. RAG interno: verificar disponibilidad, precio y stock del repuesto en el
   inventario (CSV).
3. Cruzar compatibilidad: validar que el repuesto corresponde al vehículo y
   modelo consultado (año, motor).
4. Responder con el repuesto recomendado, especificaciones técnicas, precio y
   cita de la fuente exacta (manual + código de inventario).

**Regla de seguridad no negociable:** el agente NUNCA sugiere un repuesto si no
encuentra en el inventario ni en los manuales información que respalde la
compatibilidad → responde "no tengo información suficiente" en vez de
improvisar. Repuesto en stock crítico (bajo o agotado) → alerta explícita.
Se implementará en la Fase 4 como guardrail en código (verificación post-LLM),
no solo en el prompt.

## 4. Estructura

```
EvaluacionIA1/
├── data/
│   ├── internal/inventory.csv      ✓ inventario interno (codigo, marca, precio, stock)
│   ├── external/manuales/          ✓ manuales técnicos .pdf por familia
│   ├── memory/                     ✓ memoria persistente (JSONL) del agente
│   └── exports/                    ✓ cotizaciones que escribe el agente
├── agent/
│   ├── agent.py                    ✓ orquestador: create_agent + ejecución de cada turno
│   ├── tools.py                    ✓ 6 tools: consulta, escritura y memoria
│   ├── memory.py                   ✓ memoria de corto y largo plazo (Fase 3)
│   ├── rag.py                      ✓ ingesta PDF+CSV → ChromaDB (Fase 1)
│   ├── guardrails.py               ✓ verificación post-LLM (Fase 4)
│   ├── prompts.py                  ✓ system prompt + prompts de la CLI
│   ├── llm_client.py               ✓ cliente LLM intercambiable (Groq/OpenAI) + retry 429
│   └── trace.py                    ✓ log JSONL de decisiones (Fase 3)
├── docs/
│   ├── diagramas.md                ✓ orquestación y flujos Mermaid (IE7/IE9)
│   └── CHECKLIST_ENTREGA.md        ✓ verificación + entregables AVA/email
├── ingestion/
│   └── ingest.py                   ✓ CLI de ingesta RAG (Fase 1)
├── tools/
│   └── inventory_lookup.py         ✓ búsqueda y diagnóstico sobre inventory.csv
├── web/
│   ├── server.py                   ✓ servidor HTTP + API JSON
│   └── static/index.html           ✓ interfaz: chat, búsqueda e inventario
├── main.py                         ✓ CLI marca/modelo/año → precio y stock
├── tests/
│   ├── eval_dataset.json           ✓ 15 casos con criterios y justificación
│   ├── eval_agent.py               ✓ corre la suite y genera el reporte
│   └── resultados/                 ✓ evidencia: eval_reporte.md / .json
├── scripts/
│   ├── verify_env.py               ✓ LLM, tool-calling, agente, embeddings, Chroma
│   └── generate_sample_data.py     ✓ genera inventory.csv + manuales PDF
└── requirements.txt                ✓ dependencias congeladas (pip)
```
(✓ = implementado. El informe de 5 páginas lo redacta el equipo con `docs/diagramas.md` + `tests/resultados/` como insumos.)

## 5. Plan de fases

- [x] Fase 0 — Scaffold: uv, pyproject, .env.example, verify_env.py, generate_sample_data.py, datos de ejemplo
- [x] Fase 1 — Ingesta real: PDF + CSV → chunking 500/50 → índice Chroma persistente
      (`agent/rag.py`, `ingestion/ingest.py`)
- [x] Fase 2 — Cliente LLM + prompts + cadena RAG con citas de fuente
      (`agent/llm_client.py`, `agent/prompts.py`, `agent/tools.py`)
- [x] Fase 3 — Tools de inventario/compatibilidad + `main.py` CLI + `trace.jsonl`
      (`tools/inventory_lookup.py`, `agent/trace.py`)
- [x] Fase 4 — Guardrails de seguridad: negativa sin fuente y alerta de stock
      (`agent/guardrails.py`)
- [x] Fase 5 — Evals: 15 casos (≥3 alerta/negativa), meta ≥85 % → **15/15 (100 %)**
- [x] Fase 6 — README con instrucciones precisas, estructura y referencias APA
      + `docs/diagramas.md` (orquestación y flujos Mermaid, IE7/IE9)
      + `docs/CHECKLIST_ENTREGA.md` (verificación y entregables)
- [x] Fase 6b — Interfaz web (`web/server.py` + `web/static/index.html`) y memoria
      multi-turno (`agent/memory.py`)

## 6. Limitaciones conocidas

- Los manuales técnicos y el inventario son datos de ejemplo simulados para el
  prototipo; NO son el inventario ni los manuales reales de Repuestos Sur.
  Documentar en README/informe.
- `EmbeddingModel` local: primera ejecución descarga ~470MB (una sola vez).
- El agente depende de un modelo con **tool-calling** y no todos los de Groq lo
  soportan. Si se cambia `GROQ_MODEL`, correr `scripts/verify_env.py`.
- El entorno se armó con `pip` + `requirements.txt` (D11): `uv.lock` quedó
  desactualizado respecto de `pyproject.toml` y habría que regenerarlo si se
  retoma D5.
- La memoria de largo plazo recorta por orden de llegada, no por relevancia, y
  no resuelve hechos contradictorios (limitación documentada en
  `agent/memory.py`).
- `.env` está gitignored y no viaja en git: recrearlo desde `.env.example`
  en cada checkout.
- En la máquina de desarrollo la directiva de Control de aplicaciones bloquea
  el binario nativo de `tiktoken` (`_tiktoken...pyd`), sin el cual
  `langchain_openai` no se importa. Workaround SOLO local (no va a git):
  stub puro-Python en `.venv/Lib/site-packages/sitecustomize.py`. El proyecto
  no cuenta tokens localmente (usa `usage_metadata` de la API), así que el
  stub no afecta resultados. En otra máquina no hace falta.

## 7. Historial de decisiones

- **2026-09-08** — Plan aprobado por el equipo (estructura, fases, stack).
  LangChain elegido sobre LlamaIndex (D6); ChromaDB sobre FAISS (D3), ambos
  documentados como alternativas del curso. Guardrail de seguridad definido
  como código, no solo prompt. Scaffold completado (Fase 0) siguiendo la
  estructura de `ep1-veterinaria-agente`.
- **2026-09-09** — MVP `main.py`: consola marca/modelo/año, búsqueda solo en
  `inventory.csv` (rangos de años con regex), LLM intercambiable OpenAI/Groq vía
  `LLM_PROVIDER` (se usa Groq `groq/compound-mini`, verificado contra su API),
  fallback en texto plano sin IA y encoding UTF-8 para consola Windows. Se creó
  `.env` con key de Groq (gitignored; en este checkout `.env` no está presente
  y debe recrearse). Pendiente: alinear `verify_env.py` con Groq y Fases 1–6.
- **2026-09-09** — `verify_env.py` alineado con Groq: lee `LLM_PROVIDER` y
  valida el proveedor activo (Groq con `GROQ_API_KEY` + base_url de Groq,
  OpenAI como antes). Validado de punta a punta (Groq OK, embeddings 384d,
  ChromaDB OK) y `main.py` probado (Suzuki Swift 2015 y Toyota Corolla 2018).
  Con esto la Fase 0 queda completa y verificable.
- **2026-10-06** — Evaluación 2. `groq/compound-mini` dejó de existir (404):
  se compararon 4 modelos de Groq con `tool_choice="required"` y se eligió
  `qwen/qwen3.8-27b` (D8). Se completaron Fases 1–5 con la arquitectura de
  agente (D6): `agent/{agent,tools,memory,rag,guardrails,prompts,llm_client,
  trace}.py`, `ingestion/ingest.py`, `web/` y `tests/`. Decisiones nuevas:
  memoria híbrida JSONL+Chroma (D9), guardrails en código post-LLM (D10) y
  entorno pip+requirements (D11). Dos correcciones surgidas de los evals:
  memoria aislada para los tests y system prompt reforzado (el agente afirmaba
  guardar sin llamar la tool). Evals: 15/15 (100 %). README reescrito con
  instrucciones precisas.
- **2026-10-08** — Resiliencia 429 (D12) + documentación EP2: reintentos con
  backoff solo ante límite de tasa en `agent/agent.py` y `agent/llm_client.py`
  (env `AGENT_RETRY_ATTEMPTS`/`AGENT_RETRY_BASE_S`, verificado offline:
  detección 429, backoff 20/40/60s y fallback CSV); `docs/diagramas.md`
  (orquestación y flujos Mermaid, IE7/IE9) y `docs/CHECKLIST_ENTREGA.md`.
  Entorno revalidado en esta máquina: `.venv` Python 3.12 + `requirements.txt`,
  ingesta (3 + 12 docs) y `verify_env.py` todo verde con stub local de
  `tiktoken` (bloqueado por Control de aplicaciones, no va a git).

## 8. En progreso (pausa al hacer commit — 2026-10-06)

- **Límite OTPM del plan gratuito de Groq (1000 tokens de salida/minuto).** Con
  uso intensivo (evals + pruebas) el agente a veces falla con
  `OpenAIRateLimitError` (HTTP 429). Al detectarlo en `web/server.py` la
  respuesta ya cae a "modo sin IA", pero la UX es mala.
- **Resuelto 2026-10-08 (D12):** reintentos con backoff en `agent/agent.py`
  (`_invoke_with_retry`) y `agent/llm_client.py` (`ask_llm`) solo ante 429 —
  3 intentos 20s/40s/60s configurables (`AGENT_RETRY_ATTEMPTS` /
  `AGENT_RETRY_BASE_S`); si se agotan, mensaje de saturación + fallback CSV.
  Diagramas en `docs/diagramas.md` y checklist en `docs/CHECKLIST_ENTREGA.md`.
- **Validado 2026-10-08 en esta máquina** (`.venv` Python 3.12, key Groq real):
  - `python ingestion/ingest.py --force` → manuales 3 + inventario 12 docs.
  - `python scripts/verify_env.py` → todo verde (LLM, tool-calling, agente
    6 tools, embeddings 384d, ChromaDB).
  - Hallazgo: `tiktoken` nativo bloqueado por Control de aplicaciones →
    stub local en `.venv/.../sitecustomize.py` (no va a git, ver §6).
- **Sigue pendiente:** re-correr `tests/eval_agent.py` con el retry nuevo,
  redactar el informe de 5 páginas y el commit+push final.