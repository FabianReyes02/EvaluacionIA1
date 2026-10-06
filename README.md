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
| **D. Documentación técnica** | Este README + `agents.md` (decisiones de diseño) |
| **E / F. Redacción, diagramas y flujos** | Informe del equipo + `tests/resultados/eval_reporte.md` (trazas reales) |
| **G. Referencias APA** | Sección [Referencias](#-referencias) |

## 🛠️ Tecnologías

| Capa | Elección |
|---|---|
| Lenguaje | Python 3.11+ (probado en 3.13) |
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
tabla del inventario con alertas de stock.

### 2. Línea de comandos

```bash
python main.py
```

Pide marca, modelo y año, valida los datos con el LLM y responde con precio y
stock. Sin API key cae a búsqueda directa sobre el CSV.

### 3. Evaluación (evidencia de pruebas)

```bash
python tests/eval_agent.py                 # 15 casos, meta ≥ 85%
python tests/eval_agent.py --solo C01,C07  # subconjunto
```

Salida: `tests/resultados/eval_reporte.md` y `.json` (tabla de resultados,
herramientas usadas, guardrails activados, tokens y respuesta de cada caso).

## 📁 Estructura

```
EvaluacionIA1/
├── agent/
│   ├── agent.py          Orquestador: crea el agente y ejecuta cada interaccion
│   ├── tools.py          6 herramientas (consulta / escritura / memoria)
│   ├── memory.py         Memoria de corto y largo plazo
│   ├── rag.py            Ingesta PDF+CSV -> embeddings -> ChromaDB
│   ├── guardrails.py     Verificacion POST-LLM (codigos y stock)
│   ├── prompts.py        System prompt y prompts de la CLI
│   ├── llm_client.py     Cliente LLM intercambiable (Groq/OpenAI)
│   └── trace.py          Log JSONL de las decisiones (logs/trace.jsonl)
├── tools/
│   └── inventory_lookup.py   Busqueda y diagnostico sobre el CSV
├── ingestion/
│   └── ingest.py         CLI de ingesta RAG
├── web/
│   ├── server.py         Servidor HTTP + API JSON
│   └── static/index.html Interfaz (chat + búsqueda + inventario)
├── tests/
│   ├── eval_dataset.json 15 casos con lo esperado y su justificación
│   ├── eval_agent.py     Ejecuta la suite y genera el reporte
│   └── resultados/       Evidencia generada
├── scripts/
│   ├── verify_env.py         Verifica LLM, tool-calling, agente, embeddings y Chroma
│   └── generate_sample_data.py  Genera CSV y manuales PDF de ejemplo
├── data/
│   ├── internal/inventory.csv
│   ├── external/manuales/*.pdf
│   ├── memory/           Memoria persistente del agente (JSONL)
│   └── exports/          Cotizaciones escritas por el agente
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
| `buscar_repuesto` | consulta | Repuestos compatibles con un vehículo en el CSV |
| `buscar_en_manual` | consulta | Especificaciones técnicas en los manuales PDF (RAG) |
| `verificar_compatibilidad` | consulta | Si un código sirve para un vehículo dado |
| `recuperar_memoria` | consulta | Hechos recordados de sesiones anteriores |
| `recordar_dato` | **escritura** | Persiste un dato del cliente en largo plazo |
| `exportar_cotizacion` | **escritura** | Escribe un JSON en `data/exports/` |

### Reglas de seguridad (no negociables)

Implementadas como **código** en `agent/guardrails.py`, no solo en el prompt:

- Ningún repuesto sin respaldo en el inventario ni en los manuales → responde
  *"no tengo información suficiente"*.
- Todo código mencionado se valida contra el CSV; si no existe se marca como
  `no verificado` y se avisa.
- Stock menor a 5 o agotado → alerta explícita, verificada tras la respuesta.

## ⚙️ Configuración (`.env`)

| Variable | Descripción | Default |
|---|---|---|
| `LLM_PROVIDER` | `groq` u `openai` | `groq` |
| `GROQ_API_KEY` / `OPENAI_API_KEY` | Clave del proveedor activo | — |
| `GROQ_MODEL` / `OPENAI_MODEL` | Modelo a usar | `qwen/qwen3.8-27b` / `gpt-4o-mini` |
| `EMBEDDING_MODEL` | Modelo de embeddings locales | `paraphrase-multilingual-MiniLM-L12-v2` |
| `MEMORIA_FILE` / `MEMORIA_COLLECTION` | Ruta y colección de la memoria (los tests las aíslan) | `data/memory/memoria.jsonl` / `memoria` |

## 📊 Resultado de las pruebas

Última corrida completa (`python tests/eval_agent.py`):

| | |
|---|---|
| Casos aprobados | **15/15 (100 %)** — meta ≥ 85 % |
| Cobertura | búsqueda, validación, negativas, alerta de stock, fuera de contexto, RAG, compatibilidad, guardrails, escritura y memoria entre sesiones |
| Tokens | ~46 500 |

Detalle por caso en [`tests/resultados/eval_reporte.md`](tests/resultados/eval_reporte.md).

## ⚠️ Limitaciones

- El inventario y los manuales son **datos de ejemplo simulados**, no los de la
  tienda real.
- El primer arranque descarga ~470 MB de embeddings.
- `chroma_db/`, `logs/`, `data/memory/*.jsonl` y `data/exports/` son artefactos
  generados y están en `.gitignore`.
- `uv.lock` corresponde al lock inicial del proyecto; con `pip` se usa
  `requirements.txt`.

## 📚 Referencias

- Harrison, C. (2025). *LangChain: Agents* [Documento técnico]. LangChain. https://python.langchain.com/docs/concepts/tool_calling/
- Chroma Technologies. (2025). *Chroma: The AI-native embedding database* [Documento técnico]. https://docs.trychroma.com/
- Groq. (2025). *Groq API: Fast inference for LLMs* [Documento técnico]. https://console.groq.com/docs/overview
- Reimers, N. & Gurevych, I. (2019). *Sentence-BERT: Sentence embeddings using Siamese BERT-networks*. Proceedings of EMNLP-IJCNLP. https://doi.org/10.18653/v1/D19-1410
- OpenAI. (2025). *API reference: Chat completions* [Documento técnico]. https://platform.openai.com/docs/api-reference/chat

## 👥 Equipo

**Fabián Reyes** y **Matías Vargas** — Caso organizacional: *Repuestos Sur*.
