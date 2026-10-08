# Checklist final de entrega — EP2 Repuestos Sur

## 1. Verificación técnica (en orden, desde la raíz `EvaluacionIA1/`)

```bash
copy .env.example .env   # y pegar GROQ_API_KEY real (gsk_...)
python ingestion/ingest.py --stats
python scripts/verify_env.py        # LLM + tool-calling + agente + embeddings + Chroma
python tests/eval_agent.py          # meta >= 85%; esperado 15/15
python web/server.py                # probar health, chat multi-turno, reset
```

Si `verify_env` falla por tool-calling: cambiar `GROQ_MODEL` a `openai/gpt-oss-20b`
(respaldo verificado) y re-correr.

## 2. Límite de tasa Groq (plan gratuito, 1000 OTPM)

- El agente reintenta **solo errores 429** (`agent/llm_client.py`,
  `agent/agent.py`): 3 intentos con espera 20s/40s/60s.
- Configurable: `AGENT_RETRY_ATTEMPTS=3`, `AGENT_RETRY_BASE_S=20` en `.env`.
- Si igual se agota: responde mensaje de saturación + búsqueda directa CSV
  (no cae a error seco). Evitar correr evals + web a la vez.

## 3. Entregables formales (AVA + email docente)

- [ ] Informe 5 páginas Word/PDF (A-G, IE1-IE10, redacción técnica, APA).
      Insumos: este repo + `docs/diagramas.md` + `tests/resultados/eval_reporte.md`
      + `agents.md` D1-D12.
- [ ] Enlace repo GitHub con README (instrucciones de ejecución) + diagramas.
- [ ] `commit + push` final: incluir `docs/`, `agent/` retry, README;
      NO subir `.env`, `chroma_db/`, `logs/`, `data/memory/*.jsonl`,
      `data/exports/` (gitignored, se regeneran).

## 4. Pendientes conocidos (no bloquean, documentar en informe)

- `uv.lock` desactualizado (proyecto corre con `pip` + `requirements.txt`, D11).
- Memoria largo plazo recorta por llegada, no resuelve contradicciones.
- Datos simulados (`generate_sample_data.py`), no tienda real.
