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
| **A. Agente con framework** (consulta, escritura, razonamiento) | `agent/agent.py` (`create_agent` de LangChain) + `agent/tools.py` (9 herramientas) |
| **B. Memoria corto y largo plazo** | `agent/memory.py` (ventana de 10 turnos + `memoria.jsonl`/Chroma **por usuario**, con TTL/LRU) |
| **C. Planificación y decisiones** | Loop plan→tool→observación, `agent/guardrails.py` y `tests/` |
| **D. Documentación técnica** | Este README + `agents.md` (decisiones de diseño) + `docs/diagramas.md` (orquestación y flujos, IE7) |
| **E / F. Redacción, diagramas y flujos** | Informe del equipo + `docs/diagramas.md` + `tests/resultados/eval_reporte.md` (trazas reales) |
| **G. Referencias APA** | Sección [Referencias](#-referencias) |

## 🛠️ Tecnologías

| Capa | Elección |
|---|---|
| Lenguaje | Python 3.11+ (probado en 3.12) |
| Framework de agentes | **LangChain Agents** (`langchain.agents.create_agent`) |
| LLM | Groq (`qwen/qwen3.8-27b` u `openai/gpt-oss-120b`) u OpenAI `gpt-4o-mini`, intercambiable por `LLM_PROVIDER`; en producción corre `openai/gpt-oss-120b` |
| Vector store | **ChromaDB** persistente en `chroma_db/` |
| Embeddings | `paraphrase-multilingual-MiniLM-L12-v2` locales (384d, sin costo de API) |
| Interfaz | Web con `http.server` de la stdlib; en AWS detrás de **Nginx + HTTPS** |

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
python web/server.py             # abre http://127.0.0.1:8000/login
python web/server.py 8080        # otro puerto
```

La interfaz requiere **login**. En `/register` cualquier compañero crea su
cuenta de **cliente** con usuario, contraseña y **correo electrónico**
(acepta direcciones de prueba como `probador1@lab`: no tienen que ser reales).
Ese correo queda asociado a la cuenta: cuando el cliente pida enviar una
cotización, el agente lo usa como destinatario sin volver a preguntarlo,
incluso si en el chat escribe otra dirección. Con `EMAIL_MODE="dry"` la
cotización queda preparada en un `.eml` y la herramienta lo dice
explícitamente. El **admin** (creado desde `ADMIN_USER`/`ADMIN_PASSWORD` en `.env`)
tiene `/admin` con: alta/gestión de usuarios, sesiones activas (se pueden
cerrar), auditoría de los últimos 30 días y el inventario con alertas de
stock. El cliente **no** ve inventario ni el panel.

El despliegue en AWS sirve la interfaz por **HTTPS** (`https://<IP>/`): HTTP
redirige a HTTPS, la cookie de sesión viaja con `Secure` y se envía HSTS.
Mientras no haya un dominio con ACME se usa un certificado **autofirmado**
(generado con `deploy/generar_certificado_autofirmado.sh`), así que el navegador
mostrará una advertencia que hay que aceptar una vez.

El servidor limita los chats concurrentes (`MAX_CONCURRENT_CHATS=3`), los hace
esperar hasta `CHAT_QUEUE_WAIT_S=15` y, si sigue saturado, **degrada con
elegancia**: responde `200` con búsqueda directa en el CSV (`modo_sin_ia: true`,
`saturado: true` y `retry_after`) en vez de un `503`; también aplica rate limit
por usuario/IP. Así 5-10 consultas simultáneas se turnan o caen al modo sin IA
sin tumbar el proceso ni devolver errores de servidor. Para probar carga y
permisos:

```bash
python scripts/load_test.py --url http://127.0.0.1:8000 --users 5 --requests 1 \
  --admin-user admin --admin-password '...'

# Contra el despliegue (el script acepta el certificado autofirmado):
python scripts/load_test.py --url https://<IP> --users 10 --requests 2
```

### 2. Línea de comandos

```bash
python main.py
```

Pide marca, modelo y año, valida los datos con el LLM y responde con precio y
stock. Sin API key cae a búsqueda directa sobre el CSV.

### 3. Evaluación (evidencia de pruebas)

```bash
python tests/eval_agent.py                 # 18 casos, meta ≥ 85% (pausa 15s entre casos)
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

El caso **C17 (venta)** tiene dos turnos: el primero prepara la venta y devuelve
un token, y el segundo confirma con `confirmado=true`. La evidencia 18/18 se
generó antes de ese cambio; los criterios del caso no se modificaron.

Salida: `tests/resultados/eval_reporte.md` y `.json` (tabla de resultados,
herramientas usadas, guardrails activados, reintentos por 429, tokens y
respuesta de cada caso). La corrida histórica del 2026-10-19 (suite de 15
casos) queda archivada en `eval_reporte_15casos_qwen_2026-10-19.{md,json}`.

### 4. Pruebas de las herramientas (sin gastar tokens)

```bash
python -m pytest tests -q                 # 37 pruebas: auth, tools, resiliencia y web
python scripts/verify_env.py              # LLM, tool-calling, agente, embeddings y Chroma
python scripts/p5_rate_limit_checks.py    # 429/TPD y circuit breaker, sin gastar tokens
python scripts/fuzz_public_url.py --base https://<IP>   # P3 contra el despliegue
```

Para el correo, sin pasar por el LLM:

```bash
python scripts/configurar_correo.py                 # guarda credenciales en .env (entrada oculta)
python scripts/test_email.py                        # verifica config + login SMTP, NO envía
python scripts/test_email.py --enviar tu@correo.com # envía una cotización real
python scripts/test_email.py --dry                  # deja el .eml con el PDF adjunto, no sale a internet
```

## 📁 Estructura

```
EvaluacionIA1/
├── agent/
│   ├── agent.py          Orquestador, circuit breaker y degradación elegante
│   ├── tools.py          9 herramientas (consulta, escritura, memoria, venta con doble confirmación)
│   ├── memory.py         Memoria corta (TTL/LRU) y larga por usuario (JSONL + Chroma)
│   ├── rag.py            Ingesta PDF+CSV -> embeddings -> ChromaDB
│   ├── guardrails.py     Verificación POST-LLM (códigos y stock)
│   ├── prompts.py        System prompt y prompts de la CLI
│   ├── llm_client.py     Cliente LLM intercambiable (Groq/OpenAI) + detección 429/TPD
│   └── trace.py          Log JSONL de las decisiones (logs/trace.jsonl)
├── tools/
│   ├── inventory_lookup.py   Búsqueda y diagnóstico sobre el CSV
│   ├── db.py                 Base interna SQLite: stock real, ventas y movimientos
│   ├── pdf_cotizacion.py     Genera el PDF de cotización/comprobante (sin dependencias)
│   └── email_sender.py       Armado/envío SMTP (en producción, modo dry)
├── ingestion/
│   └── ingest.py         CLI de ingesta RAG
├── web/
│   ├── server.py         Servidor HTTP + API JSON + CSP + Origin + cola de chats
│   ├── auth.py           Usuarios, sesiones, roles y auditoría (SQLite)
│   └── static/           index.html, login.html, register.html, admin.html
├── deploy/
│   ├── README_AWS.md / REINICIO_LAB.md
│   ├── nginx-repuestossur.conf   Reverse proxy HTTPS + HSTS
│   ├── repuestossur.service / repuestossur-ec2user.service
│   └── generar_certificado_autofirmado.sh
├── tests/
│   ├── eval_dataset.json / eval_agent.py
│   ├── test_auth.py / test_herramientas.py / test_resiliencia.py
│   └── resultados/       eval_reporte.*, load/ y security/ (P1–P5)
├── docs/
│   ├── diagramas.md      Orquestación y flujos (Mermaid, IE7/IE9)
│   └── CHECKLIST_ENTREGA.md  Verificación + entregables AVA/email
├── scripts/
│   ├── verify_env.py / configurar_correo.py / test_email.py / generate_sample_data.py
│   ├── load_test.py / fuzz_api_web.py / fuzz_public_url.py
│   ├── security_checks.py / simulate_malicious_payloads.py / redteam_prompts.py
│   └── p5_rate_limit_checks.py
├── data/
│   ├── internal/inventory.csv
│   ├── external/manuales/*.pdf
│   ├── memory/           Memoria persistente del agente (JSONL por usuario)
│   └── exports/          Cotizaciones del agente (PDF + JSON, .eml, envios.jsonl)
├── main.py               CLI interactiva
├── agents.md             Memoria de decisiones del equipo (D1–D21)
├── AVANCES.md            Bitácora de avances y pendientes
└── requirements.txt      Dependencias congeladas
```

## 🧠 Cómo funciona

1. **Entrada** del usuario (chat o CLI).
2. Se arma el contexto: catálogo del CSV + memoria de largo plazo **de ese
   usuario** + resumen de los últimos turnos (memoria de corto plazo) + correo
   de la cuenta si está autenticado.
3. El LLM **planifica**: elige una o varias herramientas y sus argumentos.
4. **Observa** el resultado y decide si necesita otra llamada o responde.
5. **Guardrails** re-verifican la respuesta contra el CSV: ningún código
   inventado y toda alerta de stock presente. Las ventas requieren un token de
   confirmación en una segunda llamada antes de descontar stock.
6. Se guarda la **traza** (`logs/trace.jsonl`) y se actualiza la memoria.
   Si el proveedor está saturado, el paso 3 se omite y se responde desde el CSV
   en modo sin IA, sin devolver errores 5xx.

### Herramientas disponibles

| Tool | Tipo | Para qué |
|---|---|---|
| `buscar_repuesto` | consulta | Repuestos compatibles con un vehículo en el inventario |
| `buscar_en_manual` | consulta | Especificaciones técnicas en los manuales PDF (RAG) |
| `verificar_compatibilidad` | consulta | Si un código sirve para un vehículo dado |
| `recuperar_memoria` | consulta | Hechos recordados de sesiones anteriores |
| `recordar_dato` | **escritura** | Persiste un dato del cliente en largo plazo |
| `exportar_cotizacion` | **escritura** | Escribe la cotización en **PDF** (y una copia JSON) en `data/exports/` |
| `enviar_cotizacion_email` | **escritura** | Usa el correo de la cuenta logueada y adjunta el **PDF**; con SMTP real lo envía, en `dry` deja el `.eml` |
| `registrar_venta` | **escritura** | Doble confirmación con token; registra la venta y **descuenta el stock** real |
| `recomendar_repuesto` | consulta | Recomienda el repuesto cruzando inventario, compatibilidad y manual |

### Base de datos interna, ventas y envío real por correo

El **stock real** vive en `data/internal/tienda.db` (SQLite de la stdlib, sin
dependencias nuevas): tablas `repuestos`, `ventas`, `venta_items` y
`movimientos_stock`. El CSV `data/internal/inventory.csv` sigue siendo el
catálogo (descripción, marca, precio, compatibilidad) y se re-sincroniza con el
stock después de cada venta, de modo que guardrails, tools, RAG y la interfaz
web nunca muestran existencias viejas.

- `registrar_venta` requiere **doble confirmación**: la primera llamada solo
  prepara la operación y devuelve un token (vigencia de 5 min, configurable con
  `VENTA_CONFIRMACION_TTL_S`); solo la segunda con `confirmado=true` descuenta
  stock de verdad (nunca queda negativo: la transacción se revierte completa),
  deja la venta auditada con su referencia (`V-0001`) y puede mandar el
  comprobante por correo.
- `recomendar_repuesto` es el pipeline completo del encargo: RAG interno +
  compatibilidad registrada + RAG de manuales con cita de la fuente.

El código soporta envío real (`EMAIL_MODE="smtp"`), pero **en el despliegue
actual está en `dry`**: no sale ningún correo y la herramienta lo dice. Para
activarlo, configura en `.env` (gitignored, nunca se versiona):

```bash
EMAIL_MODE="smtp"
SMTP_HOST="smtp.gmail.com"     # Outlook: smtp.office365.com
SMTP_PORT="587"
SMTP_USER="tu-correo@gmail.com"
SMTP_PASSWORD="..."             # Gmail/Outlook: CONTRASEÑA DE APLICACIÓN
SMTP_TLS="1"                   # 1 = STARTTLS (587), SMTP_SSL="1" = 465
EMAIL_FROM="Repuestos Sur"      # vacío = usa SMTP_USER
EMAIL_DOMAINS_ALLOWLIST=""      # vacío = sin restricción (necesario para @lab)
```

La herramienta nunca dice "enviada" si no lo envió: sin credenciales responde
*"preparada, NO se envió a <correo>"* (deja el `.eml` en `data/exports/`), y si
el SMTP falla informa el error.

### 📧 Envío de cotizaciones por correo

El agente **no pide la dirección**: usa el correo guardado en la cuenta con la
que se inició sesión. Llama `enviar_cotizacion_email`, que arma el cuerpo con
los precios y el stock del CSV (nunca con lo que dice el modelo), adjunta la
cotización en **PDF** y registra el resultado en `data/exports/envios.jsonl`.
Aunque el cliente escriba otra dirección en el chat, prevalece la de la cuenta.

Con SMTP real (`EMAIL_MODE="smtp"` y credenciales) el correo sale a internet.
Si no hay credenciales o está en `dry`, queda un `.eml` en `data/exports/` y la
herramienta responde *"preparada, NO se envió"*: nunca afirma un envío que no
ocurrió. En `dry` se aceptan direcciones de prueba sin TLD real (p. ej.
`probador1@lab`) porque no salen a internet.

```bash
EMAIL_MODE="smtp"
SMTP_HOST="smtp.gmail.com"     # Outlook: smtp.office365.com
SMTP_PORT="587"
SMTP_USER="tu-correo@gmail.com"
SMTP_PASSWORD="..."             # Gmail/Outlook: CONTRASEÑA DE APLICACIÓN
SMTP_TLS="1"                   # 1 = STARTTLS (587), SMTP_SSL="1" = 465
EMAIL_FROM="Repuestos Sur"      # solo nombre visible; la dirección es SMTP_USER
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
> del dry-run): quedan el PDF de la cotización (con su copia JSON) y la traza en
> `data/exports/envios.jsonl`, con `modo: "smtp"` y `enviado: true` **solo**
> si el servidor SMTP aceptó el mensaje.

### Reglas de seguridad (no negociables)

Implementadas como **código** en `agent/guardrails.py`, no solo en el prompt:

- Ningún repuesto sin respaldo en el inventario ni en los manuales → responde
  *"no tengo información suficiente"*.
- Todo código mencionado se valida contra el CSV; si no existe se marca como
  `no verificado` y se avisa.
- Stock menor a 5 o agotado → alerta explícita, verificada tras la respuesta.

Además, el acceso y el transporte están endurecidos: HTTPS con HSTS y cookie
`Secure`, CSP con nonce por respuesta (sin `unsafe-inline`), verificación de
`Origin` en escrituras, sesiones server-side, roles (cliente/admin), rate limit
y **memoria de largo plazo separada por usuario**. Las ventas requieren doble
confirmación para evitar que un solo mensaje descuente el stock.

### Resiliencia ante límite de tasa (Groq gratuito: 8 000 TPM y 200 000 TPD por modelo)

Solo los errores 429 se reintentan (4 intentos, espera 20s/40s/60s/80s) en
`agent/agent.py` + `agent/llm_client.py`; otros errores caen directo al
fallback sin duplicar llamadas. Configurable con `AGENT_RETRY_ATTEMPTS` y
`AGENT_RETRY_BASE_S`. Para los evals, la pausa `--pausa` entre casos evita
llegar al límite. Hay además un **circuit breaker** (`AGENT_CIRCUIT_THRESHOLD`/
`AGENT_CIRCUIT_COOLDOWN_S`) y una cola acotada: cuando se saturan, la web
responde `200` en modo sin IA con `retry_after`, no un `503`. La evidencia con
mocks está en `tests/resultados/security/p5_rate_limit_checks.md`.

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
| `EMAIL_MODE` | `auto` (smtp si hay credenciales, dry si no), `smtp` o `dry` | `smtp` |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` | Servidor y credenciales SMTP (Gmail/Outlook: contraseña de aplicación) | `smtp.gmail.com` / `587` / — / — |
| `SMTP_TLS` / `SMTP_SSL` / `EMAIL_TIMEOUT_S` | STARTTLS, SSL directo (465) y timeout de espera | `1` / `0` / `15` |
| `EMAIL_FROM` | Remitente con nombre visible (la dirección siempre es `SMTP_USER`) | `Repuestos Sur` |
| `EMAIL_DOMAINS_ALLOWLIST` | Dominios permitidos para envío (vacío = todos) | — (en producción, vacío) |
| `EMAIL_ALLOW_TEST_ADDRESSES` | Acepta correos tipo `algo@algo` también con SMTP configurado | — |
| `INVENTORY_PATH` / `TIENDA_DB_PATH` | CSV del catálogo y BD SQLite del stock real (los tests y evals los aíslan) | `data/internal/inventory.csv` / `data/internal/tienda.db` |
| `EXPORTS_DIR` | Carpeta de cotizaciones (PDF + JSON), `.eml` y `envios.jsonl` (los tests la aíslan) | `data/exports` |
| `ADMIN_USER` / `ADMIN_PASSWORD` / `ADMIN_EMAIL` | Admin inicial (solo si no existe otro admin) | — |
| `AUTH_DB_PATH` | BD de usuarios, sesiones y auditoría | `data/internal/auth.db` |
| `WEB_SESSION_TTL_S` / `LOGIN_MAX_ATTEMPTS` / `LOGIN_LOCKOUT_S` | Sesión, bloqueo y auditoría de login | `28800` / `5` / `900` |
| `AUDIT_RETENTION_DAYS` / `REGISTER_MAX_PER_HOUR` | Retención de auditoría y anti-spam | `30` / `50` |
| `MAX_CONCURRENT_CHATS` / `CHAT_QUEUE_WAIT_S` / `CHAT_RATE_LIMIT_PER_MIN` | Cola y rate limit de chats | `3` / `15` / `20` |
| `WEB_RETRY_WAIT_S` / `AGENT_CIRCUIT_THRESHOLD` / `AGENT_CIRCUIT_COOLDOWN_S` | Backoff máximo en web y circuit breaker | `5` / `3` / `30` |
| `REPUSTOS_HOST` / `REPUSTOS_PORT` / `REPUSTOS_HTTPS` / `REPUSTOS_ALLOWED_ORIGIN` | Bind, puerto, cookie `Secure` y CORS | `127.0.0.1` / `8000` / `1` en producción / — |
| `CHAT_SESSION_TTL_S` / `MAX_CHAT_SESSIONS` / `MAX_MEMORIA_REGISTROS` | LRU/TTL de sesiones y tope de memoria larga | `28800` / `200` / `500` |
| `VENTA_CONFIRMACION_TTL_S` | Vigencia del token de doble confirmación de venta | `300` |

La lista completa de variables y comentarios está en [`.env.example`](.env.example).

## 📊 Resultado de las pruebas

Última corrida completa de la suite (`python tests/eval_agent.py`):

| | |
|---|---|
| Casos aprobados | **18/18 (100 %)** — meta ≥ 85 % |
| Modelo | `openai/gpt-oss-120b` (Groq, 2.º respaldo de D8) |
| Cobertura | búsqueda, validación, negativas, alerta de stock, fuera de contexto, RAG, compatibilidad, guardrails, escritura, memoria entre sesiones, envío por correo, venta con descuento de stock y recomendación |
| Tokens | 101 404 (0 reintentos 429) |
| Modo de correo | **dry** — la suite no manda correos reales (`EMAIL_MODE="dry"`); el envío real está verificado aparte |
| Fecha | 2026-10-22 |

Detalle por caso en [`tests/resultados/eval_reporte.md`](tests/resultados/eval_reporte.md).

**Verificación actual del despliegue (2026-11-25):**

| Prueba | Resultado |
|---|---|
| `python -m pytest tests -q` | **37/37** |
| P1 — higiene y secretos | limpio |
| P3 — fuzz contra la URL pública (`https://`) | **15/15** |
| P4 — red team (sin el caso de correo) | 5 casos, revisados manualmente |
| P5 — 429/TPD con mocks | **14/14** |
| Carga, 10 usuarios × 2 consultas | **20/20 en 200**, 0 `503`, p95 40,3 s |

El detalle está en `tests/resultados/security/` y
`tests/resultados/load/load_test.json`. La suite de 18 casos no se re-corrío
tras el cambio a doble confirmación de C17: los criterios del caso no cambiaron.

> Corridas anteriores: **17/18 (94,4 %)** el 2026-10-22 con `qwen/qwen3.8-27b`
> (falló C18 porque el modelo pedía el tipo de repuesto en vez de llamar a la
> tool; se corrigió la regla 13 del prompt), **16/16 (100 %)** el 2026-10-21 con
> `openai/gpt-oss-120b` (archivada en
> [`eval_reporte_16casos_2026-10-21.md`](tests/resultados/eval_reporte_16casos_2026-10-21.md)),
> **15/15 (100 %)** el 2026-10-19 con `qwen/qwen3.8-27b` sobre la suite de 15
> casos (archivada en
> [`eval_reporte_15casos_qwen_2026-10-19.md`](tests/resultados/eval_reporte_15casos_qwen_2026-10-19.md)),
> y **14/16 (87,5 %)** con `openai/gpt-oss-120b` antes de arreglar el índice RAG y
> el contrato de las tools.
> La repetición de los 18 casos con `qwen/qwen3.8-27b` no se pudo completar: su
> **cuota diaria de tokens (TPD)** es una ventana **móvil de 24 h** por modelo
> (200 000 tokens) y se agotó en la corrida (197 267 usados). Cada modelo tiene
> su propio cubo, así que con el 120b la suite corre completo.

## ⚠️ Limitaciones

- El inventario y los manuales son **datos de ejemplo simulados**, no los de la
  tienda real.
- El primer arranque descarga ~470 MB de embeddings.
- `chroma_db/`, `logs/`, `data/memory/*.jsonl` y `data/exports/` son artefactos
  generados y están en `.gitignore`.
- `uv.lock` corresponde al lock inicial del proyecto; con `pip` se usa
  `requirements.txt`.
- El HTTPS del despliegue usa un certificado **autofirmado**; para quitar la
  advertencia del navegador hace falta un dominio con Certbot/ALB.
- El envío de correo sigue en **`dry`** en producción: la cotización queda
  preparada con su `.eml`, pero no sale a internet. Configurar SMTP es una
  tarea pendiente (ver `AVANCES.md`).
- La memoria de largo plazo recorta por orden de llegada y no resuelve hechos
  contradictorios (aunque ahora está separada por usuario).
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
