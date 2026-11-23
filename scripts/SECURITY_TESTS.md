# Pruebas de seguridad (P1–P6) — Repuestos Sur

Ejecutar desde la raíz del repo `EvaluacionIA1/` con un Python **3.11+** con dependencias instaladas (`pip install -r requirements.txt`).

## P1 — Higiene (sin red, sin LLM)

```bash
python scripts/security_checks.py
```

Salida: `tests/resultados/security/p1_security_checks.md` y `.json`.

## P2 — Payloads/mala entrada (sin LLM)

```bash
python scripts/simulate_malicious_payloads.py
```

Salida: `tests/resultados/security/p2_malicious_payloads.json`.

## P3 — API web local (servidor debe estar arriba)

Terminal 1:

```bash
python web/server.py 8765
```

Terminal 2:

```bash
python scripts/fuzz_api_web.py --port 8765
```

Salida: `tests/resultados/security/p3_fuzz_api.json`.

## P4 — Red team prompts (consume cuota del LLM)

```bash
python scripts/redteam_prompts.py
python scripts/redteam_prompts.py --solo P4.1
```

Salida: `tests/resultados/security/redteam_<timestamp>.json|.md`.

**Nota:** los veredictos automáticos son heurísticos; en la defensa revisar las respuestas completas.

## P5 — Resiliencia 429/TPD

Probar manualmente o con mocks (ver `agent/llm_client.py`: `is_rate_limit_error`, `is_daily_limit_error`, `ask_llm`, y `agent/agent.py`: `_invoke_with_retry`). Ejemplo rápido en REPL:

```python
from agent.llm_client import is_daily_limit_error
class E(Exception): pass
e = E("tokens per day (TPD) reached")
print(is_daily_limit_error(e))
```

## P6 — Checklist AWS/Nginx

Ver `docs/CHECKLIST_ENTREGA.md` y la sección de despliegue en el chat; repetir P3/P4 contra URL pública solo con control de costes y rate limit activo.

## Limitación actual del entorno

En esta máquina (Windows) puede no haber `python`/`py` en PATH más allá del alias de la Microsoft Store. Instala Python 3.12 desde python.org o `winget install Python.Python.3.12`, crea/activa un `.venv` y repite los comandos anteriores.
