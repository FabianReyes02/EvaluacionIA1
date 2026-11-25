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

Contra la URL pública (no gasta tokens, crea un usuario de prueba):

```bash
python scripts/fuzz_public_url.py --base https://34.201.171.124
```

Salida: `tests/resultados/security/p3_public_url.{json,md}`. Verifica HTTPS/HSTS,
CSP con nonce, cookie `Secure`, `Origin`, traversal y una ráfaga de health.

## P4 — Red team prompts (consume cuota del LLM)

```bash
python scripts/redteam_prompts.py
python scripts/redteam_prompts.py --solo P4.1
```

Salida: `tests/resultados/security/redteam_<timestamp>.json|.md`.

**Nota:** los veredictos automáticos son heurísticos; en la defensa revisar las respuestas completas. La corrida archivada omitió **P4.3** (correo) por instrucción del proyecto de no trabajar en envío de cotizaciones; P4.4 y P4.5 se revisaron manualmente como defendidos.

## P5 — Resiliencia 429/TPD

Sin gastar tokens:

```bash
python scripts/p5_rate_limit_checks.py
```

Salida: `tests/resultados/security/p5_rate_limit_checks.{json,md}`. Cubre
`is_rate_limit_error`, `is_daily_limit_error`, `daily_limit_reset_hint`, backoff,
circuit breaker y la degradación elegante a CSV.

## P6 — Checklist AWS/Nginx

Ver `docs/CHECKLIST_ENTREGA.md` (sección 3.b) y `deploy/README_AWS.md`. El
despliegue actual usa HTTPS con certificado autofirmado, HSTS, cookie `Secure`,
CSP con nonce y `Origin` verificado; la evidencia P3 pública, P4, P5 y la prueba
de carga están archivadas en `tests/resultados/`. Para un certificado confiable
hace falta un dominio con Certbot/ALB.

## Limitación actual del entorno

En esta máquina (Windows) puede no haber `python`/`py` en PATH más allá del alias de la Microsoft Store. Instala Python 3.12 desde python.org o `winget install Python.Python.3.12`, crea/activa un `.venv` y repite los comandos anteriores.
