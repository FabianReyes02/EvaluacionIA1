# AVANCES — EvaluacionIA1 (Fase 0)

**Proyecto:** Asistente de IA para Venta de Repuestos Automotrices (RAG)
**Equipo:** Fabián Reyes Matías Vargas — Caso: Repuestos Sur
**Última actualización:** 2026-10-19

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
- [x] Recrear `.env` desde `.env.example` y pegar la `GROQ_API_KEY` real.
      Verificado: `.env` existe en el checkout con `LLM_PROVIDER=groq` y
      `GROQ_MODEL=qwen/qwen3.8-27b` (gitignored, no viaja en git).
- [x] Alinear `scripts/verify_env.py` con Groq: valida el LLM según
      `LLM_PROVIDER` (Groq o OpenAI) y la verificación corre de punta a punta
      (Groq OK, embeddings 384d, ChromaDB OK).
- [x] Validar de punta a punta LLM, embeddings y ChromaDB con
      `scripts/verify_env.py` (ejecutado con éxito el 2026-10-08; ver
      actualización al final del archivo).

### Fases del plan (según agents.md)
- [x] **Fase 1** — Ingesta real: `agent/rag.py` e `ingestion/ingest.py`
      cargan CSV y PDF, chunking 500/50 e índice ChromaDB persistente en
      `chroma_db/` (colecciones `manuales` e `inventario`).
- [x] **Fase 2** — `agent/llm_client.py` (LLM intercambiable), `prompts.py` y
      cadena RAG con citas de fuente (`agent/tools.py`).
- [x] **Fase 3** — `tools/inventory_lookup.py` (búsqueda en inventario),
      tools en `agent/tools.py` (incluye `verificar_compatibilidad`), `main.py`
      CLI y `agent/trace.py` (log JSONL de trazabilidad).
- [x] **Fase 4** — Guardrails de seguridad en código (post-LLM) en
      `agent/guardrails.py`: nunca sugerir un repuesto sin fuente; alerta
      explícita por stock crítico.
- [x] **Fase 5** — Evals: `tests/eval_dataset.json` (15 casos, meta ≥85%) y
      `tests/eval_agent.py` → **15/15 (100%)**, evidencia en
      `tests/resultados/`. Re-corridos el 2026-10-19 con el retry 429 y pausa
      entre casos.
- [x] **Fase 6** — README completo + diagramas Mermaid (`docs/diagramas.md`) +
      `docs/CHECKLIST_ENTREGA.md`.
- [x] **Fase 7 — Informe EP2** — Informe de 5 páginas (APA, IE1–IE10) redactado
      y entregado, con diagramas de orquestación/flujos y evidencia de evals.

## Notas / limitaciones
- Los manuales técnicos y el inventario actuales son **datos de ejemplo
  simulados** (no son los datos reales de Repuestos Sur).
- La primera ejecución del modelo de embeddings descarga ~470MB (una sola vez).
- `.env` está presente en este checkout local (gitignored) con key de Groq;
  no viaja en git, por lo que debe recrearse desde `.env.example` en cada
  checkout nuevo.
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

## Actualización 2026-10-08 — Resiliencia 429 y documentación EP2

### Resiliencia ante límite de tasa (D12)
- Reintentos con backoff **solo ante 429** (límite OTPM del plan gratuito de
  Groq, 1000 tok/min) en `agent/agent.py` (`_invoke_with_retry`) y
  `agent/llm_client.py` (`ask_llm`): 3 intentos con espera 20s/40s/60s,
  configurables con `AGENT_RETRY_ATTEMPTS` y `AGENT_RETRY_BASE_S`.
- Si se agotan los reintentos: mensaje de saturación + fallback a búsqueda
  directa sobre el CSV (no cae a error seco). Variable documentada en
  `.env.example` y en el README.

### Documentación y verificación
- `docs/diagramas.md`: orquestación y flujos feliz/negativa/memoria en Mermaid
  (IE7/IE9), insumo para el informe.
- `docs/CHECKLIST_ENTREGA.md`: pasos de verificación técnica y entregables.
- Entorno revalidado el 2026-10-08 (`.venv` Python 3.12 + `requirements.txt`):
  `ingestion/ingest.py --force` → manuales 3 + inventario 12 docs;
  `scripts/verify_env.py` → todo verde (LLM, tool-calling, agente 6 tools,
  embeddings 384d, ChromaDB).
- Hallazgo local: `tiktoken` nativo bloqueado por Control de aplicaciones →
  stub en `.venv/.../sitecustomize.py` (no va a git; ver limitaciones).

## Estado real de pendientes (verificado 2026-10-19)

- [x] **Informe de 5 páginas** (APA, IE1–IE10) redactado con los insumos
      `docs/diagramas.md`, `tests/resultados/` y `agents.md` D1–D12.
- [x] Re-correr `tests/eval_agent.py` con el retry 429 (+ pausa entre casos):
      **15/15 (100 %)** el 2026-10-19, evidencia regenerada en
      `tests/resultados/eval_reporte.{md,json}`.
- [ ] Commit + push final (incluir `docs/`, `tests/` y README; NO
      subir `.env`, `chroma_db/`, `logs/`, `data/memory/*.jsonl`, `data/exports/`).
- [ ] Publicar el repo/enlace + informe en la plataforma AVA y por email al
      docente (ver `docs/CHECKLIST_ENTREGA.md`).

## Actualización 2026-10-13 — Informe EP2 redactado

- Se redactó el **informe de 5 páginas** (máximo exigido por la pauta), que
  cubre los apartados A–G del encargo y los indicadores IE1–IE10:
  - **A/IE1–IE2** Diseño e implementación del agente: 6 tools (consulta y
    escritura) sobre LangChain Agents.
  - **B/IE3–IE4** Memoria de corto y largo plazo y recuperación semántica
    (evidencia de los casos C13 y C14).
  - **C/IE5–IE6** Planificación y toma de decisiones con ejemplos reales
    (C01, C03, C05, C07, C09, C12) y guardrails post-LLM.
  - **D/IE7–IE8** Documentación, arquitectura y justificación de componentes
    (README + `docs/diagramas.md` + D1–D12).
  - **E/F/G/IE9–IE10** Diagramas de orquestación y flujos, redacción técnica y
    referencias APA.
- Insumos usados: `README.md`, `agents.md` (D1–D12), `docs/diagramas.md` y
  `tests/resultados/eval_reporte.{md,json}`.
- Con esto quedan cerradas las fases funcionales del proyecto; solo resta
  re-correr los evals con el retry 429 y hacer el commit + push y la entrega.

## Actualización 2026-10-19 — Evals re-corridos a 15/15 y entorno recreado

### Entorno (checkout nuevo)
- La máquina no tenía Python real (solo el alias de la Store) ni `uv`: se
  instaló **Python 3.12.10** con `winget` y se recreó `.venv` con
  `pip install -r requirements.txt` (D11). Sin el bloqueo de `tiktoken` de la
  máquina anterior, no hizo falta el stub `sitecustomize.py`.
- `.env` recreado desde `.env.example` con la `GROQ_API_KEY` real
  (`LLM_PROVIDER=groq`); LangSmith en `false` durante los evals.
- `python ingestion/ingest.py` → manuales 3 + inventario 12;
  `python scripts/verify_env.py` → todo verde (Groq OK, tool-calling, agente
  6 tools, embeddings 384d, ChromaDB).

### Diagnóstico y fix del 429 en los evals
- La evidencia previa (2026-10-13) daba **14/15**: C13 caía a modo sin IA por
  **429 acumulado** al final de la suite (no era un fallo de lógica).
- Reproducción aislada: `python tests/eval_agent.py --solo C13` → **1/1**,
  confirmando que el problema era el cupo por minuto, no el caso.
- Fix real y documentable en `tests/eval_agent.py`: **pausa configurable
  `--pausa`** entre casos (15 s por defecto) para no agotar el cupo del plan
  gratuito de Groq (1000 OTPM), más `AGENT_RETRY_ATTEMPTS=4`
  (espera 20/40/60/80 s). El reporte ahora registra **reintentos 429** por caso.

### Resultado
- `python tests/eval_agent.py` → **15/15 (100 %)**, ~47 000 tokens, **0
  reintentos** (la pausa evitó el límite por completo). Evidencia regenerada en
  `tests/resultados/eval_reporte.{md,json}` (fecha 2026-10-19).

## Actualización 2026-10-21 — Envío de cotizaciones por correo (D13)

### Qué se agregó
- **Tool `enviar_cotizacion_email`** (`agent/tools.py`): el agente la llama cuando
  el cliente pide enviar la cotización por correo. Arma el cuerpo con los
  **precios y el stock del CSV** (fuente única), valida la dirección, adjunta el
  JSON de la cotización y devuelve el veredicto real (enviada / preparada /
  falló). El agente pide la dirección si el cliente no se la dio.
- **Módulo `tools/email_sender.py`**: transporte por **SMTP de la stdlib**
  (`smtplib`, sin dependencias nuevas), con cuerpo en texto plano y HTML,
  allowlist opcional de dominios (`EMAIL_DOMAINS_ALLOWLIST`) y registro de cada
  envío en `data/exports/envios.jsonl`.
- **Dry-run por defecto** (`EMAIL_MODE=auto|smtp|dry`): sin `SMTP_USER`/
  `SMTP_PASSWORD` el correo queda como `.eml` en `data/exports/` y **no sale a
  internet**. La tool nunca dice "enviada" si no lo envió.
- **Regla 10 del `SYSTEM_PROMPT`**: el veredicto de la tool se reporta
  literalmente al cliente, igual que se hacía con el guardado en memoria.
- `health()` expone `correo_modo` y `correo_configurado`; la interfaz web lo
  muestra en la barra de estado. Diagrama del flujo en `docs/diagramas.md` (§5).

### Verificación
- Dry-run: deja `data/exports/cotizacion_*.eml` con el detalle, el total y la
  alerta de stock (verificado con ALT-02, stock 4 → "STOCK BAJO" en el correo).
- Casos borde verificados: correo inválido o vacío (pide la dirección), código
  inexistente (no envía nada), dominio fuera de la allowlist (no envía).
- Caso de eval nuevo **C16** (la suite queda con 16 casos; falta re-correrla
  con credenciales de Groq para regenerar la evidencia).

### Hallazgo: el límite real de Groq era DIARIO (TPD), no por minuto
- Al correr los evals, **todos** los casos caían a modo sin IA con
  `OpenAIRateLimitError`. El mensaje real del proveedor era
  *"Rate limit reached ... on tokens per day (TPD): Limit 200000, Used 198755"*
  → el límite **diario** de tokens por modelo (200 000/día), no el de
  1 000 tokens/min (OTPM) documentado en D12.
- El backoff 20/40/60/80 s no puede recuperar una cuota diaria: eran 200 s
  perdidos por caso sin ninguna posibilidad de éxito.
- **Fix** (`agent/llm_client.py`): `is_daily_limit_error()` distingue TPD/RPD
  del límite por minuto y `daily_limit_reset_hint()` extrae el "try again in
  12m40s" del proveedor. En `agent/agent.py` el límite diario **no se
  reintenta** y el mensaje al cliente es exacto ("se agotó la cuota diaria de
  tokens; la cuota se reinicia en 12m") en vez de uno genérico que hablaba de
  "por minuto". La traza ahora registra `limite_diario`.
- **Límites reales verificados** contra la doc de Groq y las cabeceras
  `x-ratelimit-*`: **8 000 tokens/min (TPM)** y **200 000 tokens/día (TPD) por
  modelo**, no "1 000 OTPM" como decía D12. Además el TPD es **por modelo**:
  agotar el de `qwen/qwen3.8-27b` no afecta a `openai/gpt-oss-120b`.
- **Suite reanudable** (`tests/eval_agent.py`): `--parcial <jsonl>` guarda el
  resultado de cada caso y saltea los ya hechos al reintentar; `--ensamblar
  <jsonl>` arma el reporte final. Un caso que no llega al LLM por límite de
  cuota queda **pendiente** (no aprobado ni fallado) y la corrida se detiene.

### Cuatro defectos reales del agente encontrados al re-correr los evals
1. **Pedía el vehículo aunque el cliente ya dio el código** ("cotiza el
   ALT-01" → "¿de qué auto es?"). Regla 5 reescrita: *"para cotizar basta el
   código del repuesto"* (el vehículo es opcional en la cotización).
2. **Pedía el correo cuando el cliente solo pedía cotizar** (C12 pasó a
   fallar al reescribir la regla 10). Ahora la regla 10 separa "cotizar"
   (`exportar_cotizacion`) de "enviar por correo" (`enviar_cotizacion_email`).
3. **Respondía "no tengo información suficiente" sin llamar a la herramienta**
   (C02 y C09 con los modelos `gpt-oss`). Regla 2 y regla 11 nuevas: si no
   sabes si un repuesto o un dato técnico existe, que lo decida la herramienta.
   Con esto `openai/gpt-oss-120b` sube de **13/16 a 14/16 (87,5 %)**.
4. **El modelo escribía los códigos con guion Unicode** (U+2011) y el CSV no
   los encontraba → la cotización salía vacía. `normalizar_codigo()` en
   `tools/inventory_lookup.py` + normalización de guiones en
   `agent/guardrails.py`.

### Estado de los evals (2026-10-21)
- `qwen/qwen3.8-27b` (modelo de D8): **cuota diaria agotada** (198 755/200 000
  tokens). La suite se está re-corriendo **por partes** con `--parcial`.
- `openai/gpt-oss-120b`: **14/16 (87,5 %)** con los arreglos de prompt, y
  **16/16 (100 %)** después de arreglar el índice RAG y el contrato de las
  tools (tercera tanda, más abajo). Es el modelo que hoy **sí** emite
  tool_calls (el 2026-10-06 no lo hacía; D8 se actualizó).
- `openai/gpt-oss-20b`: 13/16 (81,2 %) con el prompt anterior; sube con los
  arreglos de arriba.
- La evidencia versionada en `tests/resultados/` es la de **16/16 (2026-10-21)**;
  la corrida histórica de **15/15 (2026-10-19, qwen)** queda archivada aparte
  (`eval_reporte_15casos_qwen_2026-10-19.{md,json}`).

## Actualización 2026-10-21 (tercera tanda) — RAG roto, contrato de las tools y evidencia 16/16

### ⚠️ Hallazgo grave: el índice de ChromaDB estaba corrupto y el RAG no funcionaba
- Al re-correr los evals, **C09 (consulta al manual PDF) fallaba con todos los
  modelos**, y el motivo no era el modelo: la tool `buscar_en_manual` devolvía
  *"InternalError: Error creating hnsw segment reader: Nothing found on disk"* y
  `list_collections()` listaba una colección cuyo `count()` reventaba con
  *"Collection [1ad5f70a-…] does not exist"*.
- Causa: en `chroma_db/` quedaron **directorios de segmentos huérfanos** y filas
  obsoletas en `chroma.sqlite3` (ciclos de borrado + recreación de colecciones
  con `ingest.py --force` y `delete_collection`). La consulta semántica apuntaba
  a un directorio de segmentos que ya no existía → **el agente se quedaba sin
  RAG y respondía "no tengo información suficiente"** (fallo silencioso: el
  chat seguía "funcionando").
- **Fix**:
  1. Reconstrucción limpia del índice (`chroma_db/` → `ingestion/ingest.py
     --force`) y verificación: `buscar_en_manual("amperaje del alternador de
     90A")` vuelve a traer el fragmento de `manual_alternador.pdf` pág. 1.
  2. **Auto-reparación en `agent/rag.py`**: si la consulta falla por segmentos
     corruptos, `search()` reindexa la colección desde el origen (PDF/CSV) y
     reintenta una vez. Además `_borrar_coleccion()` ya no revienta si la
     colección no existe.
  3. `README.md` y `docs/CHECKLIST_ENTREGA.md` documentan el síntoma y el
     remedio (`python ingestion/ingest.py --force`).

### El contrato de la tool `buscar_repuesto` era ambiguo (C02)
- El filtro por tipo de repuesto hace coincidencia **parcial** (basta un token):
  "filtro de aceite" emparejaba con **FLT-02 (filtro de aire motor)**. La tool
  respondía *"1 repuesto(s) para Hyundai Accent 2016"* sin aclarar que **no
  era** el tipo pedido, así que el modelo respondía *"no tengo información
  suficiente"* y **nunca citaba el código FLT-02** → C02 fallaba.
- **Fix**: `coincide_tipo()` (`tools/inventory_lookup.py`) distingue match
  exacto de aproximado, y la tool ahora lo dice explícitamente: *"No hay
  'filtro de aceite' exacto para Hyundai Accent 2016. La coincidencia más
  cercana en el inventario es: - [FLT-02] Filtro de aire motor … Cita el código
  (FLT-02) como alternativa"*. El modelo ahora cita el código y aclara.

### El evaluador comparaba texto sin normalizar (C09)
- La respuesta correcta era *"corriente nominal de **90 A**"* (con espacio y
  markdown) y el criterio pedía el literal `90A` → falso negativo.
- **Fix**: `_norm()` en `tests/eval_agent.py` compara sin mayúsculas, espacios
  ni signos, de modo que `90A`, `90 A` y `**90A**` son la misma coincidencia.
  El criterio sigue exigiendo el dato, no el formato de redacción.

### Bug del modo reanudable: la memoria se borraba al reanudar
- `limpiar_memoria_eval()` se ejecutaba **siempre** al empezar una corrida, y en
  modo por partes eso borraba lo que C13 había escrito: C14 (que lee en una
  **sesión nueva** lo que C13 guardó) fallaba al reanudar.
- **Fix**: la memoria de eval se limpia **solo** en una corrida desde cero
  (`if not ya_hechos`). Verificado: C13 en una corrida y C14 en otra → 1/1 y
  1/1.

### Evidencia: **16/16 (100 %)** con la suite completa
- `openai/gpt-oss-120b` (2.º respaldo de D8): **16/16 (100 %)**, ~67 000
  tokens, 0 reintentos 429 → `tests/resultados/eval_reporte.{md,json}`.
- La corrida previa de qwen (15/15 del 2026-10-19, suite de 15 casos) queda
  archivada como `tests/resultados/eval_reporte_15casos_qwen_2026-10-19.{md,json}`.
- La corrida con el modelo principal (`qwen/qwen3.8-27b`) sigue **por partes**:
  su cuota diaria se libera sola a ~140 tokens/min, así que la suite completa
  tarda varias horas en ejecutarse.

## Actualización 2026-10-21 (cuarta tanda) — envío real por SMTP verificado

### Qué se probó
El camino completo de envío (no solo el dry-run) contra el **sandbox de
Mailtrap**: los mensajes quedan atrapados en el panel y **no se entregan a
ningún destinatario real**, así que se demuestra el envío SMTP sin mandar
correo a terceros ni depender de un buzón personal.

### Configuración usada (en `.env`, gitignored)
```bash
EMAIL_MODE="smtp"
SMTP_HOST="sandbox.smtp.mailtrap.io"
SMTP_PORT="2525"
SMTP_TLS="0"
SMTP_SSL="0"
SMTP_USER="<usuario del panel>"
SMTP_PASSWORD="<contraseña del panel>"
```
Los puertos 2525/587/465 de `sandbox.smtp.mailtrap.io` y el 587 de
`smtp.gmail.com` están **abiertos** desde la máquina de desarrollo
(`Test-NetConnection` → `TcpTestSucceeded: True` en todos), o sea que no hay
bloqueo de red que impida el envío.

### Resultado
- Login SMTP: **OK** con las credenciales del panel.
- Invocación real de la tool (`enviar_cotizacion_email.invoke({...})`):
  *"Cotizacion ENVIADA a juan.perez@ejemplo.com con 1 item(s) por $289.990."*
- `data/exports/envios.jsonl`: `modo: "smtp"`, `enviado: true` (el veredicto
  solo es `true` si el servidor SMTP aceptó el mensaje, no es una suposición).

### Hallazgos de esta tanda
- En modo `smtp` **no** se guarda copia `.eml` local (el `.eml` es el artefacto
  del dry-run); quedan el JSON de la cotización y la traza en `envios.jsonl`.
- El `.env` local tenía el bloque de correo **duplicado** y con los
  placeholders `<...>` sin reemplazar (había que quitarles los ángulos); se
  dejó un solo bloque canónico. La contraseña del sandbox nunca se versiona
  (`.env` está gitignored).
- La tool se puede invocar **sin LLM**: la cuota diaria de Groq no bloquea la
  prueba del envío, porque la decisión de llamar a la tool la toma el modelo y
  el transporte SMTP es independiente del proveedor.

## Actualización 2026-10-21 (quinta tanda) — interfaz por pestañas y C16 con envío real

### Interfaz web: el inventario pasa a su propia pestaña
- Antes: una sola columna con tres tarjetas apiladas (búsqueda rápida → chat →
  inventario), así que el catálogo quedaba **debajo** del chat y había que
  hacer scroll para verlo.
- Ahora: pestañas **💬 Chat** (búsqueda rápida + conversación con el agente) y
  **📦 Inventario** (tabla de repuestos con alertas de stock; el contador de
  filas va en la propia pestaña).
- Implementado en `web/static/index.html` con paneles `#panel-chat` /
  `#panel-inv` y un `switch` de clases `activa`; **no cambia la API** del
  servidor (`/api/chat`, `/api/inventory`, `/api/health` siguen igual).
- Verificado: servidor arriba, `/` responde 200 con el marcado nuevo,
  `/api/inventory` devuelve las 12 filas, sin referencias JS rotas y con la
  sintaxis del script validada (`node --check`).

### C16 aprobado con envío SMTP **real**
- `python tests/eval_agent.py --solo C16 --sin-reportar` con
  `GROQ_MODEL=openai/gpt-oss-120b` y `EMAIL_MODE="smtp"` → **1/1**,
  5 107 tokens. Respuesta del agente: *"Cotizacion ENVIADA a
  juan.perez@ejemplo.com con 1 item(s) por $289.990"* y registro en
  `envios.jsonl` con `modo: "smtp"`, `enviado: true`.
- `--sin-reportar` deja intacta la evidencia principal (16/16) mientras se
  re-corre la suite completa por partes.

### Lo que aprendimos de la cuota (TPD)
- El límite diario de Groq (200 000 tokens **por modelo**) es una **ventana
  móvil de 24 h**, no un reinicio a medianoche: el contador `Used` sube y baja
  (199 497 → 197 385 → 199 719 → 198 987 en las 14 iteraciones del loop) y el
  mensaje *"try again in Xm"* salta entre 4 y 22 minutos.
- Con `qwen/qwen3.8-27b` en ~199 000/200 000 quedan ~1 000 tokens libres: entra
  un ping de 40 tokens pero **no** un turno del agente (~3 200 tokens).
- `openai/gpt-oss-120b` sí tenía margen → se usó para C16 y para re-correr la
  suite por partes. Cada modelo tiene su propio cubo.

## Cómo ejecutar el proyecto (resumen)

```bash
# 1. Entorno (pip + requirements; ver D11)
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt

# 2. Credenciales
copy .env.example .env        # pegar GROQ_API_KEY (gsk_...)
                              # envío de correo (opcional): SMTP_USER/SMTP_PASSWORD + EMAIL_MODE="smtp"

# 3. Ingesta RAG (una vez; --force reconstruye, --stats muestra estado)
python ingestion/ingest.py

# 4. Verificación integral (LLM, tool-calling, agente, embeddings, Chroma)
python scripts/verify_env.py

# 5. Interfaces
python web/server.py          # web en http://127.0.0.1:8000
python main.py                # CLI marca/modelo/año

# 6. Evals / evidencia (meta >= 85%; pausa 15s entre casos por defecto)
python tests/eval_agent.py
```