# P5 — Límites de tasa y circuit breaker (generado)
Fecha: 2026-11-24T23:41:36
Resultado: 14/14 correctos

| Caso | Descripción | Resultado | Detalle |
|---|---|---|---|
| P5.1a | is_rate_limit_error(RateLimitError) | OK | esperado=True, obtenido=True |
| P5.1b | is_rate_limit_error(OpenAIRateLimitError) | OK | esperado=True, obtenido=True |
| P5.1c | is_rate_limit_error(ErrorGenerico) | OK | esperado=True, obtenido=True |
| P5.1d | is_rate_limit_error(ErrorGenerico) | OK | esperado=False, obtenido=False |
| P5.2a | detecta TPD | OK | Rate limit reached on tokens per day (TPD): Limit 200000 |
| P5.2b | no confunde TPM con TPD | OK | Rate limit reached, try again in 20s |
| P5.3 | parsea tiempo de reinicio | OK | obtenido='12m' |
| P5.3b | parsea horas | OK | obtenido='1h 5m' |
| P5.4 | backoff creciente | OK | esperas=[20.0, 40.0, 60.0], base=20.0 |
| P5.5a | se abre tras 2 429 | OK | fallos=2 |
| P5.5b | un OK reinicia el contador sin acortar el enfriamiento | OK | fallos=0, sigue abierto hasta el cooldown |
| P5.5c | se cierra solo tras el cooldown | OK | cooldown vencido |
| P5.5d | TPD no dispara circuit breaker | OK | limite_diario=True reinicia el contador |
| P5.6 | saturación devuelve 200 con CSV | OK | retry_after=7 |
