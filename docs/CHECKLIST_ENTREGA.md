# Checklist final de entrega — EP2 Repuestos Sur

## 1. Verificación técnica (en orden, desde la raíz `EvaluacionIA1/`)

```bash
copy .env.example .env   # y pegar GROQ_API_KEY real (gsk_...)
python ingestion/ingest.py --stats
python scripts/verify_env.py        # LLM + tool-calling + agente + embeddings + Chroma
python tests/eval_agent.py          # meta >= 85%; esperado 18/18 (pausa 15s entre casos)
python web/server.py                # probar health, chat multi-turno, reset
```

Si `verify_env` falla por tool-calling: cambiar `GROQ_MODEL` a `openai/gpt-oss-20b`
(respaldo verificado) y re-correr.

## 1.a Si el RAG no encuentra los manuales (D14)

Síntoma: el agente responde "no tengo información suficiente" a una pregunta que
**sí** está en los manuales PDF, y en la consola aparece
`Error creating hnsw segment reader: Nothing found on disk` (o
`Collection [...] does not exist`): el índice de ChromaDB quedó inconsistente
(segmentos huérfanos en `chroma_db/`).

```bash
python ingestion/ingest.py --force   # reconstruye las colecciones manuales e inventario
python scripts/verify_env.py         # confirma que el RAG recupera
```

`agent/rag.py` **se auto-repara**: si una consulta falla por segmentos
corruptos, reindexa la colección desde el origen y reintenta una vez.

## 1.b Verificación del envío de cotizaciones por correo (D13)

Dos formas de verificarlo, ninguna gasta tokens del LLM:

```bash
python scripts/configurar_correo.py                  # pide cuenta + contraseña de
                                                     # aplicación (entrada oculta), escribe
                                                     # el bloque en .env y prueba el login
python scripts/test_email.py                         # config + login SMTP, NO envía
python scripts/test_email.py --enviar tu@correo.com  # envío real de una cotización
python scripts/test_email.py --dry                   # deja el .eml, no sale a internet
```

Desde el agente (chat o web): *"Cotiza el ALT-01 y envíamela a juan@ejemplo.com"*.
Si no se da la dirección, el agente la pide antes de llamar a la tool.

Comportamiento esperado:

- **`EMAIL_MODE="smtp"` (default)**: el correo sale de verdad. El veredicto
  solo es `enviado: true` si el servidor SMTP aceptó el mensaje.
- **`EMAIL_MODE="dry"`** (o sin credenciales): no sale nada a internet; queda el
  `.eml` en `data/exports/` y la tool responde *"preparada, NO se envió"*.
- Cada envío queda registrado en `data/exports/envios.jsonl` (tipo,
  destinatario, modo, enviado y detalle).
- `EMAIL_DOMAINS_ALLOWLIST` restringe los dominios de destino (vacío = todos).

**Verificado el 2026-10-22 con Gmail real** (contraseña de aplicación,
`smtp.gmail.com:587` + STARTTLS): login OK y envío OK tanto desde
`scripts/test_email.py` como desde el agente (`enviado: true` en
`envios.jsonl`). El 2026-10-21 se había verificado contra el sandbox de
Mailtrap. Para no mandar correos durante los evals:
`EMAIL_MODE="dry" python tests/eval_agent.py`.

## 2. Límite de tasa Groq (plan gratuito: 8 000 TPM y 200 000 TPD por modelo)

- El agente reintenta **solo errores 429** (`agent/llm_client.py`,
  `agent/agent.py`): 4 intentos con espera 20s/40s/60s/80s.
- Configurable: `AGENT_RETRY_ATTEMPTS=4`, `AGENT_RETRY_BASE_S=20` en `.env`.
- Si igual se agota: responde mensaje de saturación + búsqueda directa CSV
  (no cae a error seco).
- **Para los evals** usar la pausa entre casos: `python tests/eval_agent.py`
  espera 15s entre casos por defecto (`--pausa S` para ajustar, `--pausa 0`
  para desactivar). Evita que un 429 tire un caso a modo sin IA. No correr
  evals + web a la vez.
- **Ojo con el límite DIARIO de tokens (TPD)**: son dos límites distintos y
  ambos aplican **por modelo** (el de uno no gasta el del otro):
  - **TPM** (por minuto): 8 000 tokens/min → es el que dispara el 429 con
    "try again in Xs" y sí se puede reintentar esperando.
  - **TPD** (por día): 200 000 tokens/día por modelo. La suite completa de 18
    casos gasta ~50 000. Si se agota, el agente lo detecta **aparte**
    (`is_daily_limit_error`), **no reintenta** (esperar 20-80s no sirve: la
    cuota se libera con el correr de la ventana de ~24 h) y avisa
    *"se agotó la cuota diaria; se reinicia en X"*.
- **Suite reanudable** (cuando el TPD no alcanza para los 18 casos de una vez):
  ```bash
  python tests/eval_agent.py --parcial tests/resultados/eval_parcial.jsonl   # corre y guarda caso a caso
  python tests/eval_agent.py --ensamblar tests/resultados/eval_parcial.jsonl # arma el reporte final
  ```
  El runner saltea los casos ya hechos y, si el proveedor corta por cuota,
  deja el caso **pendiente** (no aprobado ni fallado) y se detiene para no
  gastar cuota en casos que tampoco podrían ejecutarse.

## 3. Entregables formales (AVA + email docente)

- [ ] Informe 5 páginas Word/PDF (A-G, IE1-IE10, redacción técnica, APA).
      Insumos: este repo + `docs/diagramas.md` + `tests/resultados/eval_reporte.md`
      + `agents.md` D1-D14.
- [ ] Enlace repo GitHub con README (instrucciones de ejecución) + diagramas.
- [ ] `commit + push` final: incluir `docs/`, `agent/` retry, README;
      NO subir `.env`, `chroma_db/`, `logs/`, `data/memory/*.jsonl`,
      `data/exports/` (gitignored, se regeneran).

## 3.a Evidencia de pruebas que se entrega

| Archivo | Contenido |
|---|---|
| `tests/resultados/eval_reporte.md` / `.json` | **18/18 (100 %)** — suite completa de 18 casos (incluye C16 correo, C17 venta y C18 recomendación), modelo `openai/gpt-oss-120b`, 2026-10-22, 101 404 tokens, 0 reintentos. Corrida con `EMAIL_MODE="dry"` (los evals no mandan correos reales) |
| `tests/resultados/eval_reporte_16casos_2026-10-21.md` / `.json` | **16/16 (100 %)** — corrida histórica con envío SMTP real a Mailtrap, 2026-10-21 |
| `tests/resultados/eval_reporte_15casos_qwen_2026-10-19.md` / `.json` | **15/15 (100 %)** — corrida histórica con `qwen/qwen3.8-27b` (suite de 15 casos), 2026-10-19 |

## 3.b Pendientes conocidos (no bloquean, documentar en informe)

- `uv.lock` desactualizado (proyecto corre con `pip` + `requirements.txt`, D11).
- Memoria largo plazo recorta por llegada, no resuelve contradicciones.
- Datos simulados (`generate_sample_data.py`), no tienda real.
- El envío de correo está verificado **en los dos modos**: `smtp` (default, envío
  real con `modo: "smtp"` y `enviado: true` en `data/exports/envios.jsonl`) y
  `dry-run` (deja el `.eml` en `data/exports/`). La corrida de evidencia del
  2026-10-21 se hizo en modo `smtp` (destino: sandbox de Mailtrap, que retiene
  los mensajes y no los entrega a nadie); el 2026-10-22 se validó además con
  **Gmail real** y contraseña de aplicación.
