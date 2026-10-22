# 🚗 Asistente de IA para Venta de Repuestos Automotrices (RAG + Agente)

**ISY0101 · Ingeniería de Soluciones con IA · Evaluación Parcial**

> Repositorio con el código fuente, la documentación de funcionamiento y la
> evidencia de pruebas del agente de la tienda **Repuestos Sur**.

## 📌 Descripción

Agente conversacional que asista a vendedores y clientes a identificar el
repuesto correcto cruzando dos fuentes:

- **Fuente interna:** `data/internal/inventory.csv` → código, descripción,
  precio, stock y vehículos compatibles.
- **fuente externa:** `data/external/manuales/*.pdf` → especificaciones
  técnicas, recuperadas con RAG (ChromaDB + embeddings locales).

El agente usa **LangChain Agents** y decide por sí mismo qué herramienta
llamar, con qué argumentos y cuándo detenerse.

### Requisitos que cubre

| Apartado | Dónde está implementado |
|---|---|
| **A. Agente con framework** (consulta, escritura, razonamiento) | `agent/agent.py` (`create_agent` de LangChain) + `agent/tools.py` (6 tools) |
| **B. Memoria corto y largo plazo** | `agent/memory.py` (ventana de 10 turnos + `memoria.jsonl` + colección Chroma) |
| **C. Planificación y decisiones** | Loop plan→tool→observación, `agent/guardrails.py` y `tests/` |
| **D. Documentación técnica** | Este README + `agents.md` (decisiones de diseño) + `docs/diagramas.md` (orquestación y flujos, IE7) |
| **E / F. Redacción, diagramas y flujos** | Informe del equipo + `docs/diagramas.md` + `tests/resultados/eval_reporte.md` (trazas reales) |
| **G. Referencias APA** | Sección [Referencias](#-referencias) |

## 🛠️ Tecnologías

| Capa | Elección |
|---|---|
| Lenguaje | Python 3.11+ (probado en 3.12) |
| Framework de agentes | **LangChain Agents** (`langchain.agents.create_agent`) |
| LLM | Groq `qwen/qwen3.8-27b` (gratis) u OpenAI `gpt-4o-mini`, intercambiable por `LLM_PROVIDER` |
| Vector store | **ChromaDB** persistente en `chroma_db/` |
| Embeddings | `paraphrase-multilingual-MiniLM-L12-v2` locales (384d, sin costo de API) |
| Interfaz | Página web local servida con la estándar `http.server` (sin frameworks) |

## ⚙️ Instalación

Requisitos: **Python 3.11 o superior** e internet (la primera vez se descarga
el modelo de embeddings, ~470 MB).

```bash
# 1. Clonar
git clone https://github.com/FabianReyes02/EvaluacionIA1.git
cd EvaluacionIA1

# 2. Crear el entorno virtual e instalar dependencias
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt

# 3. Credenciales
copy .env.example .env          # Linux/macOS: cp .env.example .env
```

Edita `.env` y pega tu clave:

```env
LLM_PROVIDER="groq"
GROQ_API_KEY="gsk_..."
GROQ_MODEL="qwen/qwen3.8-27b"
```

> ⚠️ El modelo **debe soportar tool-calling**; `groq/compound-mini` y
> `allam-2-7b` **no** lo soportan. `scripts/verify_env.py` lo verifica.

## 🚀 Ejecución

Paso previo único — indexar los manuales y el inventario:

```bash
python ingestion/ingest.py        # --force reconstruye, --stats muestra estado
```

Verificar que todo funciona (LLM, tool-calling, agente, embeddings, ChromaDB):

```bash
python scripts/verify_env.py
```

### 1. Interfaz web (recomendada)

```bash
python web/server.py             # abre http://127.0.0.1:8000
python web/server.py 8080        # otro puerto
```

Incluye búsqueda rápida por marca/modelo/año, chat libre con historial y la
tabla del inventario con alertas de stock. La interfaz tiene **dos pestañas**:
**💬 Chat** (búsqueda rápida + conversación con el agente) y **📦 Inventario**
(tabla de repuestos con el contador de stock), de modo que el catálogo no
queda apilado debajo del chat.

### 2. Línea de comandos

```bash
python main.py
```

Pide marca, modelo y año, valida los datos con el LLM y responde con precio y
stock. Sin API key cae a búsqueda directa sobre el CSV.

### 3. Evaluación (evidencia de pruebas)

```bash
python tests/eval_agent.py                 # 16 casos, meta ≥ 85% (pausa 15s entre casos)
python tests/eval_agent.py --solo C01,C07  # subconjunto
python tests/eval_agent.py --pausa 0       # sin pausa (proveedor de pago / cuota amplia)
```

La pausa entre casos (`--pausa`, 15s por defecto) evita agotar el cupo del plan
gratuito de Groq (**8 000 tokens/min y 200 000 tokens/día por modelo**), que sin
ella hace caer casos sueltos a modo sin IA por error 429.

Si el **cuota diaria** no alcanza para la suite completa, se puede correr por
partes (el runner reanuda donde quedó):

```bash
python tests/eval_agent.py --parcial tests/resultados/eval_parcial.jsonl  # corre y guarda caso a caso
python tests/eval_agent.py --ensamblar tests/resultados/eval_parcial.jsonl # arma el reporte final
```

Un caso que no alcanza a llegar al LLM por límite de cuota del proveedor queda
**pendiente** (no cuenta como aprobado ni como fallado) y la corrida se detiene
para no gastar cuota en casos que tampoco podrían ejecutarse.

Salida: `tests/resultados/eval_reporte.md` y `.json` (tabla de resultados,
herramientas usadas, guardrails activados, reintentos por 429, tokens y
respuesta de cada caso). La corrida histórica del 2026-10-19 (suite de 15
casos) queda archivada en `eval_reporte_15casos_qwen_2026-10-19.{md,json}`.

## 📁 Estructura

```
EvaluacionIA1/
├── agent/
│   ├── agent.py          Orquestador: crea el agente y ejecuta cada interaccion
│   ├── tools.py          7 herramientas (consulta / escritura / memoria)
│   ├── memory.py         Memoria de corto y largo plazo
│   ├── rag.py            Ingesta PDF+CSV -> embeddings -> ChromaDB
│   ├── guardrails.py     Verificacion POST-LLM (codigos y stock)
│   ├── prompts.py        System prompt y prompts de la CLI
│   ├── llm_client.py     Cliente LLM intercambiable (Groq/OpenAI)
│   └── trace.py          Log JSONL de las decisiones (logs/trace.jsonl)
├── tools/
│   ├── inventory_lookup.py   Busqueda y diagnostico sobre el CSV
│   └── email_sender.py       Armado y envio del correo (SMTP, dry-run por defecto)
├── ingestion/
│   └── ingest.py         CLI de ingesta RAG
├── web/
│   ├── server.py         Servidor HTTP + API JSON
│   └── static/index.html Interfaz (chat + búsqueda + inventario)
├── tests/
│   ├── eval_dataset.json 16 casos con lo esperado y su justificación
│   ├── eval_agent.py     Ejecuta la suite y genera el reporte
│   └── resultados/       Evidencia generada (eval_reporte.{md,json} + corrida 15/15 archivada)
├── docs/
│   ├── diagramas.md      Orquestación y flujos (Mermaid, IE7/IE9)
│   └── CHECKLIST_ENTREGA.md  Verificación + entregables AVA/email
├── scripts/
│   ├── verify_env.py         Verifica LLM, tool-calling, agente, embeddings y Chroma
│   └── generate_sample_data.py  Genera CSV y manuales PDF de ejemplo
├── data/
│   ├── internal/inventory.csv
│   ├── external/manuales/*.pdf
│   ├── memory/           Memoria persistente del agente (JSONL)
│   └── exports/          Cotizaciones escritas por el agente (JSON, .eml, envios.jsonl)
├── main.py               CLI interactiva
├── agents.md             Memoria de decisiones del equipo
└── requirements.txt      Dependencias congeladas
```

## 🧠 Cómo funciona

1. **Entrada** del usuario (chat o CLI).
2. Se arma el contexto: catálogo del CSV + memoria de largo plazo + resumen de
   los últimos turnos (memoria de corto plazo).
3. El LLM **planifica**: elige una o varias herramientas y sus argumentos.
4. **Observa** el resultado y decide si necesita otra llamada o responde.
5. **Guardrails** re-verifican la respuesta contra el CSV: ningún código
   inventado y toda alerta de stock presente.
6. Se guarda la **traza** (`logs/trace.jsonl`) y se actualiza la memoria.

### Herramientas disponibles

| Tool | Tipo | Para qué |
|---|---|---|
| `buscar_repuesto` | consulta | Repuestos compatibles con un vehículo en el inventario |
| `buscar_en_manual` | consulta | Especificaciones técnicas en los manuales PDF (RAG) |
| `verificar_compatibilidad` | consulta | Si un código sirve para un vehículo dado |
| `recuperar_memoria` | consulta | Hechos recordados de sesiones anteriores |
| `recordar_dato` | **escritura** | Persiste un dato del cliente en largo plazo |
| `exportar_cotizacion` | **escritura** | Escribe un JSON en `data/exports/` |
| `enviar_cotizacion_email` | **escritura** | Envía la cotización por correo (SMTP real) |
| `registrar_venta` | **escritura** | Registra la venta y **descuenta el stock** en la BD interna |
| `recomendar_repuesto` | consulta | Recomienda el repuesto cruzando inventario, compatibilidad y manual |

### Base de datos interna, ventas y envío real por correo

El **stock real** vive en `data/internal/tienda.db` (SQLite de la stdlib, sin
dependencias nuevas): tablas `repuestos`, `ventas`, `venta_items` y
`movimientos_stock`. El CSV `data/internal/inventory.csv` sigue siendo el
catálogo (descripción, marca, precio, compatibilidad) y se re-sincroniza con el
stock después de cada venta, de modo que guardrails, tools, RAG y la interfaz
web nunca muestran existencias viejas.

- `registrar_venta` descuenta stock de verdad (nunca queda negativo: la
  transacción se revierte completa), deja la venta auditada con su referencia
  (`V-0001`) y puede mandar el comprobante por correo.
- `recomendar_repuesto` es el pipeline completo del encargo: RAG interno +
  compatibilidad registrada + RAG de manuales con cita de la fuente.

El envío de correo es **real por defecto** (`EMAIL_MODE="smtp"`). Configura en
`.env` (gitignored, nunca se versiona):

```bash
EMAIL_MODE="smtp"
SMTP_HOST="smtp.gmail.com"     # Outlook: smtp.office365.com
SMTP_PORT="587"
SMTP_USER="tu-correo@gmail.com"
SMTP_PASSWORD="..."             # Gmail/Outlook: CONTRASEÑA DE APLICACIÓN
SMTP_TLS="1"                   # 1 = STARTTLS (587), SMTP_SSL="1" = 465
EMAIL_FROM="Repuestos Sur"      # vacío = usa SMTP_USER
EMAIL_DOMAINS_ALLOWLIST="gmail.com,ejemplo.com"   # vacío = sin restricción
```

La herramienta nunca dice "enviada" si no lo envió: sin credenciales responde
*"preparada, no se envió"* (deja el `.eml` en `data/exports/`), y si el SMTP
falla informa el error.

### 📧 Envío de cotizaciones por correo

El agente pide la dirección del cliente si no se la dieron y luego llama
`enviar_cotizacion_email`, que arma el cuerpo del correo **con los precios y el
stock del CSV** (nunca con lo que dice el modelo), adjunta el JSON de la
cotización y registra el envío en `data/exports/envios.jsonl`.

Por defecto el envío es **real por SMTP** (`EMAIL_MODE="smtp"`): el correo sale
a internet y queda registrado en `data/exports/envios.jsonl`. Si el servidor SMTP
no está configurado, el correo queda como `.eml` en `data/exports/` (modo
dry-run) y la herramienta lo dice: nunca afirma un envío que no ocurrió.

```bash
EMAIL_MODE="smtp"
SMTP_HOST="smtp.gmail.com"     # Outlook: smtp.office365.com
SMTP_PORT="587"
SMTP_USER="tu-correo@gmail.com"
SMTP_PASSWORD="..."             # Gmail/Outlook: CONTRASEÑA DE APLICACIÓN
SMTP_TLS="1"                   # 1 = STARTTLS (587), SMTP_SSL="1" = 465
EMAIL_FROM="Repuestos Sur <cotizaciones@repuestosur.cl>"
EMAIL_DOMAINS_ALLOWLIST=""     # ej: "clientesur.cl" (vacío = sin restricción)
```

La herramienta nunca dice "enviada" si no lo envió: sin credenciales responde
*"preparada, no se envió"*, y si el SMTP falla informa el error.

#### Probarlo sin usar tu correo real: sandbox de Mailtrap

Mailtrap captura los mensajes en su panel y **no los entrega a nadie**, así que
sirve para demostrar el envío real sin mandar nada a terceros (en el inbox del
panel → *SMTP Credentials*):

```bash
EMAIL_MODE="smtp"
SMTP_HOST="sandbox.smtp.mailtrap.io"
SMTP_PORT="2525"
SMTP_TLS="0"                   # 2525 sin cifrado (587 = STARTTLS, 465 = SSL)
SMTP_SSL="0"
SMTP_USER="<usuario del panel>"
SMTP_PASSWORD="<contraseña del panel>"
```

> En modo `smtp` **no** se guarda copia `.eml` local (el `.eml` es el artefacto
> del dry-run): quedan el JSON de la cotización y la traza en
> `data/exports/envios.jsonl`, con `modo: "smtp"` y `enviado: true` **solo**
> si el servidor SMTP aceptó el mensaje.

### Reglas de seguridad (no negociables)

Implementadas como **código** en `agent/guardrails.py`, no solo en el prompt:

- Ningún repuesto sin respaldo en el inventario ni en los manuales → responde
  *"no tengo información suficiente"*.
- Todo código mencionado se valida contra el CSV; si no existe se marca como
  `no verificado` y se avisa.
- Stock menor a 5 o agotado → alerta explícita, verificada tras la respuesta.

### Resiliencia ante límite de tasa (Groq gratuito: 8 000 TPM y 200 000 TPD por modelo)

Solo los errores 429 se reintentan (4 intentos, espera 20s/40s/60s/80s) en
`agent/agent.py` + `agent/llm_client.py`; otros errores caen directo al
fallback sin duplicar llamadas. Configurable con `AGENT_RETRY_ATTEMPTS` y
`AGENT_RETRY_BASE_S`. Para los evals, la pausa `--pausa` entre casos evita
llegar al límite.

El plan gratuito también tiene un **límite diario de tokens (TPD)**: cuando se
agota, la cuota no se recupera esperando en la misma sesión (se reinicia a la
medianoche del proveedor). Por eso el agente **detecta el límite diario por
separado**, no reintenta en vano y responde *"se agotó la cuota diaria de
tokens; la cuota se reinicia en 12m"* en vez de un mensaje genérico. En ese
caso el agente cae igual a modo sin IA (búsqueda directa en el CSV).

## 🗺️ Diagramas

Orquestación, flujos feliz/negativa y memoria en [`docs/diagramas.md`](docs/diagramas.md)
(Mermaid, renderiza en GitHub). Checklist de verificación y entrega en
[`docs/CHECKLIST_ENTREGA.md`](docs/CHECKLIST_ENTREGA.md).

## ⚙️ Configuración (`.env`)

| Variable | Descripción | Default |
|---|---|---|
| `LLM_PROVIDER` | `groq` u `openai` | `groq` |
| `GROQ_API_KEY` / `OPENAI_API_KEY` | Clave del proveedor activo | — |
| `GROQ_MODEL` / `OPENAI_MODEL` | Modelo a usar | `qwen/qwen3.8-27b` / `gpt-4o-mini` |
| `EMBEDDING_MODEL` | Modelo de embeddings locales | `paraphrase-multilingual-MiniLM-L12-v2` |
| `MEMORIA_FILE` / `MEMORIA_COLLECTION` | Ruta y colección de la memoria (los tests las aíslan) | `data/memory/memoria.jsonl` / `memoria` |
| `AGENT_RETRY_ATTEMPTS` / `AGENT_RETRY_BASE_S` | Reintentos solo ante 429 y espera base (20s,40s,60s,80s) | `4` / `20` |
| `EMAIL_MODE` | `auto` (smtp si hay credenciales, dry si no), `smtp` o `dry` | `auto` |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` | Servidor y credenciales SMTP (Gmail/Outlook: contraseña de aplicación) | `smtp.gmail.com` / `587` / — / — |
| `SMTP_TLS` / `SMTP_SSL` / `EMAIL_TIMEOUT_S` | STARTTLS, SSL directo (465) y timeout de espera | `1` / `0` / `15` |
| `EMAIL_FROM` | Remitente con nombre visible | `Repuestos Sur <cotizaciones@repuestosur.cl>` |
| `EMAIL_DOMAINS_ALLOWLIST` | Dominios permitidos para envío (vacío = todos) | — |

## 📊 Resultado de las pruebas

Última corrida completa de la suite (`python tests/eval_agent.py`):

| | |
|---|---|
| Casos aprobados | **16/16 (100 %)** — meta ≥ 85 % |
| Modelo | `openai/gpt-oss-120b` (Groq, 2.º respaldo de D8) |
| Cobertura | búsqueda, validación, negativas, alerta de stock, fuera de contexto, RAG, compatibilidad, guardrails, escritura, memoria entre sesiones y envío por correo |
| Tokens | 66 712 (0 reintentos 429) |
| Modo de correo | **smtp** — el caso C16 envió el correo de verdad (sandbox de Mailtrap: queda atrapado en el panel, no llega a nadie) |
| Fecha | 2026-10-21 |

Detalle por caso en [`tests/resultados/eval_reporte.md`](tests/resultados/eval_reporte.md).

> Corridas anteriores: **15/15 (100 %)** el 2026-10-19 con
> `qwen/qwen3.8-27b` (modelo principal de D8) sobre la suite de 15 casos, y
> **14/16 (87,5 %)** con `openai/gpt-oss-120b` antes de arreglar el índice RAG y
> el contrato de las tools. La corrida del 2026-10-19 está archivada en
> [`eval_reporte_15casos_qwen_2026-10-19.md`](tests/resultados/eval_reporte_15casos_qwen_2026-10-19.md).
> La corrida con `qwen/qwen3.8-27b` sobre los 16 casos no se ha podido
> completar: su **cuota diaria de tokens (TPD)** es una ventana **móvil de 24 h**
> por modelo (200 000 tokens) y al agotarse solo se liberan unos ~30 tokens/min
> (los tokens van saliendo de la ventana conforme envejecen las peticiones).
> Cada modelo tiene su propio cubo, así que con el 120b la suite sí corre
> completo.

## ⚠️ Limitaciones

- El inventario y los manuales son **datos de ejemplo simulados**, no los de la
  tienda real.
- El primer arranque descarga ~470 MB de embeddings.
- `chroma_db/`, `logs/`, `data/memory/*.jsonl` y `data/exports/` son artefactos
  generados y están en `.gitignore`.
- `uv.lock` corresponde al lock inicial del proyecto; con `pip` se usa
  `requirements.txt`.
- **Si el agente responde "no tengo información suficiente" a una consulta que
  sí está en los manuales**, el índice de ChromaDB puede estar corrupto (síntoma
  típico: `Error creating hnsw segment reader: Nothing found on disk`). La
  búsqueda **se auto-repara** (reindexa y reintenta), pero conviene reconstruirlo
  a mano: `python ingestion/ingest.py --force`.

## 📚 Referencias

- Harrison, C. (2025). *LangChain: Agents* [Documento técnico]. LangChain. https://python.langchain.com/docs/concepts/tool_calling/
- Chroma Technologies. (2025). *Chroma: The AI-native embedding database* [Documento técnico]. https://docs.trychroma.com/
- Groq. (2025). *Groq API: Fast inference for LLMs* [Documento técnico]. https://console.groq.com/docs/overview
- Reimers, N. & Gurevych, I. (2019). *Sentence-BERT: Sentence embeddings using Siamese BERT-networks*. Proceedings of EMNLP-IJCNLP. https://doi.org/10.18653/v1/D19-1410
- OpenAI. (2025). *API reference: Chat completions* [Documento técnico]. https://platform.openai.com/docs/api-reference/chat

## 👥 Equipo

**Fabián Reyes** y **Matías Vargas** — Caso organizacional: *Repuestos Sur*.
