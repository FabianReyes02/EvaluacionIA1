# agents.md — Memoria de decisiones y avance del semestre

**Proyecto:** EvaluacionIA1 (Asistente de IA para Venta de Repuestos Automotrices)
**Curso:** ISY0101 Ingeniería de Soluciones con IA — Evaluación Parcial 2 (35%)
**GitHub:** https://github.com/FabianReyes02/EvaluacionIA1
**Última actualización:** 2026-10-21

> Memoria técnica del proyecto. Se actualiza en cada sesión para preservar
> decisiones, tradeoffs y avance entre entregas. Sirve de bitácora para el
> docente (IE7/IE8: justificar decisiones) y para el equipo.

## 1. Contexto del semestre

- EP2 = 1 caso organizacional + informe de 5 páginas APA (IE1–IE10). Se
  desarrolla en parejas, 2 semanas.
- Caso organizacional: **Repuestos Sur** — tienda de repuestos automotrices
  que necesita asistir a vendedores/clientes para identificar repuestos
  correctos cruzando manuales técnicos (PDF) con el inventario interno (CSV).
- Regla del stack: **≥50% con tecnologías vistas en clase es concepto guía,
  no requisito literal.** El profesor alienta la exploración. Toda tecnología
  fuera del curso debe quedar justificada aquí y en el informe.

## 2. Decisiones cerradas

| # | Decisión | Elección | Justificación | Alternativa descartada |
|---|---|---|---|---|
| D1 | Proveedor LLM | OpenAI (`gpt-4o-mini`) o Groq (`qwen/qwen3.8-27b`, gratis) intercambiable vía `LLM_PROVIDER` en `.env` (default actual: `groq`) | API OpenAI-compatible y ampliamente documentada; Groq sin costo para el prototipo. Anthropic documentado como alternativa, aún no implementado | Proveedor local sin API |
| D2 | Embeddings | `paraphrase-multilingual-MiniLM-L12-v2` local (384d) | Contenido en español; costo 0 y privado | `all-MiniLM-L6-v2` (enfoque inglés) |
| D3 | Vector store | **ChromaDB** persistente en `chroma_db/` sobre FAISS | Filtro nativo por metadata (`marca`, `categoria`, `tipo_fuente`); API simple. FAISS se documenta como alternativa del curso (RA1/IL1.3) | FAISS |
| D4 | Chunking | Manuales PDF con `RecursiveCharacterTextSplitter`-style 500/50 (visto en RA1/IL1.3); entradas de inventario (CSV) completas por fila | Fragmentos de manual deben recuperarse íntegros para mantener especificaciones coherentes (compatibilidad, medidas) | Chunk grande genérico |
| D5 | Gestor de deps | uv + Python 3.11 | Convención del curso (uv.lock en repo materiales) | pip |
| D6 | Orquestación | **LangChain** (chains RAG + document loaders de la comunidad) | README del proyecto lo indica; versiones y ecosistema maduros | LlamaIndex (documentado como alternativa) |
| D7 | Datos | Ejemplo generado por `scripts/generate_sample_data.py` (CSV inventario + PDF manuales técnicos) | Escasez de datos reales; replicable y versionable | Datos externos sin licenciar |
| D8 | Modelo LLM | Groq `qwen/qwen3.8-27b` (antes `groq/compound-mini`) | El anterior respondía 404; se probaron 4 modelos con `tool_choice="required"` y solo `qwen3.8-27b` y `gpt-oss-20b` emitían tool_calls. Qwen eligió la tool correcta con argumentos precisos en los 4 escenarios de prueba. **Re-verificado 2026-10-21:** `openai/gpt-oss-120b` **también** emite tool_calls hoy (D8 lo había descartado el 2026-10-06) y sirve de segundo respaldo; `gpt-oss-20b` es el más débil (13-14/16) | `openai/gpt-oss-120b` (no llamó tools el 2026-10-06), `allam-2-7b` (sin soporte) |
| D9 | Memoria | Corto plazo: ventana de 10 turnos por sesión en memoria. Largo plazo: `data/memory/memoria.jsonl` **+** colección Chroma con recuperación semántica, escrita/leída por tools que el agente decide llamar | Cumple "corto y largo plazo" con una sola tecnología ya presente; el JSONL garantiza persistencia aunque Chroma falle | Solo `ConversationBuffer` (sin persistencia) o base vectorial dedicada |
| D10 | Guardrails | Verificación **post-LLM** en `agent/guardrails.py`: todo código mencionado se contrasta con el CSV y todo stock crítico exige alerta | La regla es no negociable y un prompt no garantiza el comportamiento (el agente llegó a decir que guardó un dato sin llamar la tool) | Confiar solo en el system prompt |
| D11 | Entorno | `pip` + `.venv` (Python 3.12 verificado el 2026-10-13; antes 3.13 en otra máquina) con `requirements.txt` congelado | `uv` no estaba disponible en la máquina de desarrollo; se priorizó poder ejecutar y evaluar el agente | Instalar uv y regenerar `uv.lock` (pendiente si se retoma D5) |
| D12 | Resiliencia 429 | Reintentos con backoff **solo ante límite de tasa** en `agent/agent.py` + `agent/llm_client.py` (4 intentos, 20s/40s/60s/80s, env `AGENT_RETRY_ATTEMPTS`/`AGENT_RETRY_BASE_S`); mensaje amable + fallback CSV si se agotan. En evals, **pausa configurable `--pausa`** (15s por caso) para no agotar el cupo. **El límite diario de tokens (TPD) se detecta aparte** (`is_daily_limit_error`): no se reintenta (esperar 20-80s no sirve si la cuota reinicia a la medianoche) y el mensaje dice que la cuota se reinicia en X. **Suite reanudable**: `tests/eval_agent.py --parcial/--ensamblar` corre los casos de a uno y arma el reporte al final; un caso bloqueado por cuota queda pendiente, no aprobado ni fallado | El plan gratuito Groq limita a 8 000 TPM y **200 000 TPD por modelo** (no 1 000 OTPM como se creía; son 2 límites distintos y confundirlos hacía gastar 200 s por caso en reintentos inútiles). El TPD se agota en una ventana de ~24 h: reintentar no lo recupera, solo lo corre la ventana | Reintentar errores genéricos, solo confiar en el fallback seco, o perder la corrida completa cuando el cuota no alcanza |
| D13 | Envío de cotizaciones por correo | Tool `enviar_cotizacion_email` (`agent/tools.py`) + módulo `tools/email_sender.py` sobre **SMTP de la stdlib** (`smtplib`), **dry-run por defecto**: sin credenciales el correo queda como `.eml` en `data/exports/` y no sale a internet. Allowlist opcional de dominios (`EMAIL_DOMAINS_ALLOWLIST`) y registro de cada envío en `data/exports/envios.jsonl` | Cero dependencias nuevas y cero API keys: SMTP con contraseña de aplicación funciona en Gmail/Outlook. El dry-run evita que un prototipo o una corrida de evals mande un correo real por error, y el `.eml` deja el cuerpo exacto para revisión. El cuerpo se arma con los precios del CSV, no con lo que dice el modelo. **Verificado con envío real el 2026-10-21** contra el sandbox de Mailtrap (`modo: "smtp"`, `enviado: true` solo si el servidor SMTP aceptó el mensaje; los correos quedan atrapados en el panel de Mailtrap y no llegan a ningún destinatario real) | API de proveedor (SendGrid/Resend/Brevo: clave + dependencia extra), o envío real sin dry-run (un error del LLM llega al cliente) |
| D14 | Robustez del RAG y contrato de las tools | `agent/rag.py` **se repara solo**: si la consulta a ChromaDB falla por segmentos corruptos, reindexa la colección desde el origen (PDF/CSV) y reintenta una vez. Las tools devuelven un mensaje **inequívoco**: el filtro por tipo distingue match exacto de aproximado (`coincide_tipo()`) y lo dice ("no hay 'filtro de aceite' exacto; la más cercana es FLT-02") | Un RAG caído **falla en silencio**: el chat sigue respondiendo, pero sin evidencia el agente degradaba a "no tengo información suficiente" y perdía el caso de eval (C09). Y una tool ambigua hace que el modelo ignore el dato que sí tenía (C02: nunca citaba FLT-02) | Dejar que la tool devuelva un listado sin contexto, o que el RAG degrade sin avisar, o "arreglar" el prompt para tapar un bug de la tool |

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
│   ├── memory/                     ◌ runtime (gitignored): `memoria.jsonl` / `memoria_eval.jsonl` se crean al ejecutar; no se versiona
│   └── exports/                    ◌ runtime (gitignored): cotizaciones que escribe el agente (JSON, .eml preparados y envios.jsonl)
├── agent/
│   ├── agent.py                    ✓ orquestador: create_agent + ejecución de cada turno
│   ├── tools.py                    ✓ 7 tools: consulta, escritura y memoria
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
│   ├── inventory_lookup.py         ✓ búsqueda y diagnóstico sobre inventory.csv
│   └── email_sender.py             ✓ armado y envío del correo (SMTP stdlib, dry-run por defecto)
├── web/
│   ├── server.py                   ✓ servidor HTTP + API JSON
│   └── static/index.html           ✓ interfaz: chat, búsqueda e inventario
├── main.py                         ✓ CLI marca/modelo/año → precio y stock
├── tests/
│   ├── eval_dataset.json           ✓ 16 casos con criterios y justificación
│   ├── eval_agent.py               ✓ corre la suite y genera el reporte
│   └── resultados/                 ✓ evidencia: eval_reporte.md / .json
├── scripts/
│   ├── verify_env.py               ✓ LLM, tool-calling, agente, embeddings, Chroma
│   └── generate_sample_data.py     ✓ genera inventory.csv + manuales PDF
└── requirements.txt                ✓ dependencias congeladas (pip)
```
(✓ = implementado y versionado en git; ◌ = runtime gitignored que se genera al ejecutar. El informe de 5 páginas ya está redactado usando `docs/diagramas.md` + `tests/resultados/` + D1–D12 como insumos.)

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
- [x] Fase 5 — Evals: 16 casos (≥3 alerta/negativa), meta ≥85 % → **16/16 (100 %)** el
      2026-10-21 con `openai/gpt-oss-120b` (suite de 16, incluye el envío por correo);
      la corrida de **15/15 (100 %)** del 2026-10-19 con `qwen/qwen3.8-27b` queda
      archivada en `tests/resultados/eval_reporte_15casos_qwen_2026-10-19.md`
- [x] Fase 6 — README con instrucciones precisas, estructura y referencias APA
      + `docs/diagramas.md` (orquestación y flujos Mermaid, IE7/IE9)
      + `docs/CHECKLIST_ENTREGA.md` (verificación y entregables)
- [x] Fase 6b — Interfaz web (`web/server.py` + `web/static/index.html`) y memoria
      multi-turno (`agent/memory.py`)
- [x] Fase 7 — Informe EP2 de 5 páginas (APA, A–G, IE1–IE10) redactado con
      diagramas de orquestación/flujos (`docs/diagramas.md`) y evidencia de
      evals (`tests/resultados/`)

## 6. Limitaciones conocidas

- Los manuales técnicos y el inventario son datos de ejemplo simulados para el
  prototipo; NO son el inventario ni los manuales reales de Repuestos Sur.
  Documentar en README/informe.
- `EmbeddingModel` local: primera ejecución descarga ~470MB (una sola vez).
- El agente depende de un modelo con **tool-calling** y no todos los de Groq lo
  soportan. Si se cambia `GROQ_MODEL`, correr `scripts/verify_env.py`.
- El entorno se armó con `pip` + `requirements.txt` (D11): `uv.lock` quedó
  desactualizado respecto de `pyproject.toml` y habría que regenerarlo si se
  retoma D5. Igual `.python-version` sigue en 3.11 mientras el `.venv`
  verificado corre Python 3.12.10.
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
  stub no afecta resultados. En otra máquina no hace falta. (Al recrear el
  entorno el 2026-10-19 con Python 3.12.10 no se reprodujo y no hizo falta.)

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
- **2026-10-13** — Informe EP2 redactado: documento de 5 páginas (máximo
  exigido) que cubre los apartados A–G del encargo y los indicadores IE1–IE10,
  apoyado en `README.md`, `docs/diagramas.md`, `tests/resultados/` y las
  decisiones D1–D12. Con esto se cierran las fases funcionales; resta re-correr
  los evals con el retry 429 y la entrega (commit + push + AVA + email).
- **2026-10-19** — Evals re-corridos a **15/15 (100 %)**. En un checkout nuevo
  (sin Python ni `.venv`) se instaló Python 3.12.10 con `winget` y se recreó el
  entorno con `pip` + `requirements.txt`; ingesta y `verify_env.py` verdes. La
  evidencia previa daba 14/15 porque C13 caía a modo sin IA por **429
  acumulado**; aislado pasaba (1/1), así que se añadió **pausa configurable
  `--pausa`** (15s) entre casos en `tests/eval_agent.py` y se subió
  `AGENT_RETRY_ATTEMPTS=4`. La corrida completa salió 15/15 con **0
  reintentos** (evidencia regenerada en `tests/resultados/`). D12 ampliada.
- **2026-10-21** — **Envío de cotizaciones por correo (D13).** Se agregó la tool
  `enviar_cotizacion_email` (`agent/tools.py`) sobre el módulo nuevo
  `tools/email_sender.py`: arma el cuerpo del correo con los precios y el stock
  del CSV (fuente única), valida la dirección, aplica allowlist opcional de
  dominios y deja el envío registrado en `data/exports/envios.jsonl`.
  Transporte por SMTP de la stdlib (`smtplib`, sin dependencias nuevas) con
  **dry-run por defecto**: sin `SMTP_USER`/`SMTP_PASSWORD` el correo queda
  como `.eml` en `data/exports/` y **no sale a internet**; la tool nunca dice
  "enviada" si no lo envió. La regla 10 del `SYSTEM_PROMPT` obliga a pedir la
  dirección al cliente si no la dio y a reportar literalmente el veredicto de
  la tool. Caso de eval nuevo **C16** (16 casos).
- **2026-10-21 (segunda tanda) — cuota diaria agotada + robustez del agente.**
  Al correr los evals, **todos** los casos caían a modo sin IA: el error real
  del proveedor era *"Rate limit reached ... on tokens per day (TPD): Limit
  200000, Used 198755"*. Se corrigió el manejo (detección aparte del límite
  diario, sin reintentos inútiles, mensaje exacto con el tiempo de reinicio) y
  se hizo la **suite reanudable** (`--parcial` / `--ensamblar`). En el camino
  aparecieron y se corrigieron cuatro defectos reales del agente:
  1. el modelo pedía marca/modelo/año aunque el cliente ya había dado el
     **código** (regla 5 reescrita: *"para cotizar basta el código"*);
  2. la regla 10 mezclaba cotizar con enviar por correo, así que pedía el
     correo cuando el cliente solo pedía cotizar (ahora son dos reglas);
  3. el modelo respondía *"no tengo información suficiente"* **sin llamar a la
     herramienta** (regla 2 y regla 11: si no sabes si existe, que lo decida
     la herramienta);
  4. el modelo escribía los códigos con guion Unicode (U+2011) y el CSV no los
     encontraba → `normalizar_codigo()` en `tools/inventory_lookup.py` y
     normalización de guiones en `agent/guardrails.py`.
  Con esos cambios, `openai/gpt-oss-120b` (que el 2026-10-06 no llamaba tools
  y hoy sí) sube de 13/16 a **14/16 (87,5 %)** y `qwen/qwen3.8-27b` (modelo de
  D8, con la cuota diaria agotada) es el que se está re-corriendo por partes.
- **2026-10-21 (tercera tanda) — el RAG estaba roto y dos tools/evaluadores
  eran ambiguos.** Con la suite de 16 casos, **C09 fallaba con todos los
  modelos** y el culpable no era el modelo: `buscar_en_manual` reventaba con
  *"Error creating hnsw segment reader: Nothing found on disk"* porque en
  `chroma_db/` quedaron **segmentos huérfanos** y filas obsoletas en
  `chroma.sqlite3` (ciclos de borrado + recreación de colecciones). El RAG
  **fallaba en silencio**: el chat seguía respondiendo, pero sin evidencia el
  agente degradaba a "no tengo información suficiente". Se reconstruyó el
  índice y se añadió **auto-reparación** (D14): si la consulta falla,
  `search()` reindexa desde el origen y reintenta. Además:
  1. `buscar_repuesto` filtraba el tipo de repuesto con coincidencia **parcial**
     ("filtro de aceite" → FLT-02, que es *filtro de aire*) sin decirlo, y el
     modelo terminaba respondiendo "no tengo información suficiente" **sin
     citar el código** → ahora `coincide_tipo()` distingue match exacto de
     aproximado y la tool pide explícitamente citar la alternativa (D14);
  2. el evaluador comparaba texto sin normalizar: la respuesta correcta
     "corriente nominal de **90 A**" no era el literal `90A` del criterio →
     `_norm()` ahora iguala `90A`, `90 A` y `**90A**`;
  3. en modo reanudable, `limpiar_memoria_eval()` borraba lo que C13 había
     escrito y C14 (que lee en sesión nueva) fallaba → la memoria de eval solo
     se limpia en una corrida desde cero.
  Con los cuatro arreglos la suite completa da **16/16 (100 %)** con
  `openai/gpt-oss-120b` (evidencia regenerada en `tests/resultados/`; la
  corrida histórica de 15/15 del 2026-10-19 queda archivada). La corrida con
  `qwen/qwen3.8-27b` sigue por partes: su cuota diaria se libera sola a
  ~140 tokens/min.
- **2026-10-21 (cuarta tanda) — envío real por SMTP verificado.** Se probó el
  camino completo de envío contra el **sandbox de Mailtrap**
  (`sandbox.smtp.mailtrap.io:2525`, sin cifrado): los mensajes quedan atrapados
  en el panel de Mailtrap y **no se entrega a ningún destinatario real**, así
  que se puede demostrar el envío SMTP sin mandar correo a terceros. Login
  OK con las credenciales del panel y envío OK: la tool respondió
  *"Cotizacion ENVIADA a juan.perez@ejemplo.com con 1 item(s) por $289.990"*
  y `data/exports/envios.jsonl` registró `modo: "smtp"`, `enviado: true`
  (el veredicto solo es `true` si el servidor SMTP aceptó el mensaje). De paso
  se detectó que en modo `smtp` **no** se guarda copia `.eml` local (el `.eml`
  es el artefacto del dry-run): quedan el JSON de la cotización y la traza en
  `envios.jsonl`. Además se limpió el `.env` local, que tenía el bloque de
  correo duplicado y los placeholders `<...>` sin reemplazar (la contraseña
  del sandbox nunca se versiona: `.env` está gitignored).
- **2026-10-21 (quinta tanda) — la interfaz web pasa a pestañas.** El
  inventario estaba apilado **debajo del chat** y hundía la conversación en
  scroll. Ahora `web/static/index.html` tiene dos paneles conmutables:
  **💬 Chat** (búsqueda rápida + conversación) y **📦 Inventario** (tabla de
  repuestos, con el contador de stock en la pestaña). Es solo HTML/CSS/JS: no
  cambia la API del servidor (`/api/chat`, `/api/inventory`, `/api/health`).
- **La cuota del plan Groq es una ventana MÓVIL de 24 h, no un reinicio
  diario.** El contador `Used` del TPD (200 000 tokens/día **por modelo**) sube
  y baja según las peticiones van saliendo de la ventana; por eso el mensaje
  *"try again in Xm"* salta de 4 m a 22 m entre intentos. Verificado el
  2026-10-21: `qwen/qwen3.8-27b` estaba en ~199 000/200 000 (un turno del
  agente pide ~3 200 tokens → no entra) mientras que
  `openai/gpt-oss-120b` sí tenía margen (C16 aprobado con envío SMTP real:
  5 107 tokens). **Cada modelo tiene su propio cubo**: el agotamiento de uno
  no afecta al otro.

## 8. En progreso (actualizado 2026-10-21)

- **Límite de tasa del plan gratuito de Groq: son DOS límites, no uno.** El
  real es **8 000 tokens/min (TPM) y 200 000 tokens/día (TPD) por modelo**
  (verificado en las cabeceras `x-ratelimit-*` y en la doc de Groq; lo de
  "1 000 OTPM" era incorrecto). Con uso intensivo (evals + pruebas) el agente
  falla con `OpenAIRateLimitError` (HTTP 429) y cae a "modo sin IA".
- **Resuelto 2026-10-08 (D12):** reintentos con backoff en `agent/agent.py`
  (`_invoke_with_retry`) y `agent/llm_client.py` (`ask_llm`) solo ante 429 —
  4 intentos 20s/40s/60s/80s configurables (`AGENT_RETRY_ATTEMPTS` /
  `AGENT_RETRY_BASE_S`); si se agotan, mensaje de saturación + fallback CSV.
  Diagramas en `docs/diagramas.md` y checklist en `docs/CHECKLIST_ENTREGA.md`.
- **Validado 2026-10-08 en esta máquina** (`.venv` Python 3.12, key Groq real):
  - `python ingestion/ingest.py --force` → manuales 3 + inventario 12 docs.
  - `python scripts/verify_env.py` → todo verde (LLM, tool-calling, agente
    7 tools, embeddings 384d, ChromaDB).
  - Hallazgo: `tiktoken` nativo bloqueado por Control de aplicaciones →
    stub local en `.venv/.../sitecustomize.py` (no va a git, ver §6).
- **Informe EP2 redactado (2026-10-13):** el informe de 5 páginas (A–G,
  IE1–IE10) quedó listo a partir de `docs/diagramas.md`, `tests/resultados/` y
  las decisiones D1–D12.
- **Evals re-corridos (2026-10-19):** `tests/eval_agent.py` → **15/15 (100 %)**
  con retry 429 y pausa `--pausa` entre casos; 0 reintentos. Evidencia
  regenerada en `tests/resultados/`.
- **Evals de la suite de 16 casos (2026-10-21):** **16/16 (100 %)** con
  `openai/gpt-oss-120b` (66 712 tokens, 0 reintentos). Evidencia en
  `tests/resultados/eval_reporte.{md,json}`; la corrida histórica de 15/15
  (qwen, 2026-10-19) archivada en
  `tests/resultados/eval_reporte_15casos_qwen_2026-10-19.{md,json}`. Esta
  corrida se hizo en **modo `smtp`**: el caso **C16 aprobada con el envío
  real** (el agente respondió *"Cotización enviada a juan.perez@ejemplo.com"*).
  La corrida con `qwen/qwen3.8-27b` (modelo principal de D8) **no se pudo
  completar**: su TPD es una ventana móvil de 24 h que se agotó y solo libera
  ~30 tokens/min.
- **RAG reparado (2026-10-21, D14):** el índice de ChromaDB tenía segmentos
  huérfanos y el RAG **fallaba en silencio** (C09 perdía con todos los
  modelos). Índice reconstruido + auto-reparación en `agent/rag.py`
  (reindexa y reintenta si la consulta falla). Si vuelve a pasar:
  `python ingestion/ingest.py --force`.
- **Envío de cotizaciones por correo (2026-10-21, D13):** listo y verificado en
  modo dry-run (tool `enviar_cotizacion_email`: validación del correo,
  allowlist de dominios, `.eml` en `data/exports/`, registro en
  `envios.jsonl`, alerta de stock en el cuerpo) y con el caso de eval **C16**
  aprobado. **Envío real verificado el 2026-10-21** contra el sandbox de
  Mailtrap (`sandbox.smtp.mailtrap.io:2525`, sin cifrado): la tool respondió
  *"Cotizacion ENVIADA…"* y `envios.jsonl` quedó con `modo: "smtp"` y
  `enviado: true`. Para enviar a una casilla real: `SMTP_USER`/`SMTP_PASSWORD`
  en `.env` (Gmail/Outlook: contraseña de aplicación) con `EMAIL_MODE="smtp"`.
- **Sigue pendiente:** commit + push y entrega final (AVA + email docente).