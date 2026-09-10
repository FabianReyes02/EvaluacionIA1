# agents.md — Memoria de decisiones y avance del semestre

**Proyecto:** EvaluacionIA1 (Asistente de IA para Venta de Repuestos Automotrices)
**Curso:** ISY0101 Ingeniería de Soluciones con IA — Evaluación Parcial 1 (30%)
**GitHub:** https://github.com/FabianReyes02/EvaluacionIA1
**Última actualización:** 2026-09-09

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
│   ├── internal/inventory.csv      ✓ (inventario interno: codigo, marca, categoria,
│   │                                vehiculos compatibles, precio, stock)
│   └── external/manuales/          ✓ (manuales técnicos .pdf por familia de repuesto)
├── ingestion/ingest.py             (plan, Fase 1) carga PDF + CSV → chunk → embed → Chroma
├── agent/
│   ├── llm_client.py               (plan, Fase 2) cliente LLM intercambiable (OpenAI/Groq)
│   ├── qa_chain.py                 (plan, Fase 2) chain RAG LangChain (recupera + responde)
│   ├── prompts.py                  (plan, Fase 2)
│   └── trace.py                    (plan, Fase 3) log JSONL de trazabilidad
├── tools/
│   ├── inventory_lookup.py         (plan, Fase 3) busca repuesto en inventory.csv (metadatos)
│   └── compatibility_checker.py    (plan, Fase 3) valida vehículo/modelo vs especificaciones
├── main.py                         ✓ MVP CLI: marca/modelo/año → repuestos del CSV con
│                                    precio, stock y alerta (aún sin RAG ni citas de manual)
├── tests/
│   ├── eval_dataset.json           (plan, Fase 5) 12-15 casos con resultado esperado
│   └── eval_agent.py               (plan, Fase 5) corre evals y reporta % de aciertos
├── scripts/
│   ├── verify_env.py               ✓ (verifica datos y OpenAI; pendiente alinear con Groq)
│   └── generate_sample_data.py     ✓ genera inventory.csv + manuales PDF de ejemplo
└── docs/                           (plan, Fase 6) informe y diagramas
```
(✓ = implementado; los demás archivos son plan de las Fases 1–6)

## 5. Plan de fases

- [x] Fase 0 — Scaffold: uv, pyproject, .env.example, verify_env.py, generate_sample_data.py, datos de ejemplo
- [ ] Fase 1 — Ingesta real (csv + pdf loaders), chunking e índice Chroma persistent
- [ ] Fase 2 — llm_client.py + prompts + chain RAG base con citas
- [ ] Fase 3 — Tools inventario/compatibilidad + main.py CLI + trace.jsonl
      (adelanto parcial: `main.py` MVP ya existe, sin `tools/` ni trace)
- [ ] Fase 4 — Guardrails de seguridad (negativa sin fuente, alertas de stock)
- [ ] Fase 5 — Evals: 12-15 casos (≥3 alerta/negativa), meta ≥85% aciertos
- [ ] Fase 6 — README completo + diagrama Mermaid + docs/informe

## 6. Limitaciones conocidas

- Los manuales técnicos y el inventario son datos de ejemplo simulados para el
  prototipo; NO son el inventario ni los manuales reales de Repuestos Sur.
  Documentar en README/informe.
- `EmbeddingModel` local: primera ejecución descarga ~470MB (una sola vez).
- `main.py` (MVP) solo cruza el inventario CSV; aún no recupera manuales PDF
  (RAG = Fases 1–2) ni valida compatibilidad en profundidad ni cita fuentes.
- `.env` está gitignored y no viaja en git: recrearlo desde `.env.example`
  en cada checkout.
- `verify_env.py` valida únicamente `OPENAI_API_KEY`; con `LLM_PROVIDER=groq`
  el check del LLM aún no aplica (pendiente alinear).

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