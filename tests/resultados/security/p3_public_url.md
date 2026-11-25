# P3 — Fuzz contra la URL pública (generado)
Fecha: 2026-11-24T23:41:43
Base: https://34.201.171.124
Resultado: 15/15 correctos

| Caso | Resultado | Detalle |
|---|---|---|
| P3.1 | OK | health -> 200 |
| P3.2 | OK | HSTS presente en health |
| P3.3 | OK | HTTP -> 301 https://34.201.171.124/api/health |
| P3.4 | OK | / anonimo -> 303 |
| P3.5 | OK | /admin anonimo -> 303 |
| P3.6 | OK | /api/inventory anonimo -> 401 |
| P3.7 | OK | CSP con nonce y sin unsafe-inline |
| P3.8 | OK | registro de prueba -> 200 |
| P3.9 | OK | login -> 200, cookie Secure=True |
| P3.10 | OK | Content-Type incorrecto -> 415 |
| P3.11 | OK | cuerpo grande -> 400 |
| P3.12 | OK | traversal -> 400 (Nginx puede rechazar con 400 antes de la app) |
| P3.13 | OK | traversal -> 400 (Nginx puede rechazar con 400 antes de la app) |
| P3.14 | OK | Origin cross-site -> 403 |
| P3.15 | OK | 20 GET paralelos: todos 200? True |
