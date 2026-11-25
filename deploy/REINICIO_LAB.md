# Reabrir el laboratorio y volver a acceder al despliegue

Cada sesión nueva de AWS Academy entrega **credenciales temporales nuevas** y
la IP pública de tu máquina puede cambiar. La instancia EC2 **persiste** entre
sesiones (no hay que redeployar), pero al apagarse/encenderse cambia su **IP
pública**. Por eso “no funciona” casi siempre significa una de estas tres
cosas:

1. credenciales vencidas (`ExpiredToken`),
2. regla SSH del Security Group apuntando a tu IP vieja,
3. IP de la instancia distinta a la que tenés anotada.

## Paso a paso (Windows + PowerShell)

### 1. Credenciales nuevas

Copiá el bloque `AWS CLI` que muestra el lab. **No lo pegues en un chat**;
configurá un perfil local:

```powershell
aws configure --profile repuestos
# Access Key ID, Secret Access Key, Session token, región: us-east-1
aws sts get-caller-identity --profile repuestos --query Account --output text
# debe imprimir 765062702015
```

Si usás variables de entorno en cambio:

```powershell
$env:AWS_ACCESS_KEY_ID='...'
$env:AWS_SECRET_ACCESS_KEY='...'
$env:AWS_SESSION_TOKEN='...'
$env:AWS_DEFAULT_REGION='us-east-1'
```

### 2. Tu IP pública actual y la IP de la instancia

```powershell
$miIp = (Invoke-RestMethod 'https://checkip.amazonaws.com').Trim()
$miIp

aws ec2 describe-instances --profile repuestos --region us-east-1 `
  --query 'Reservations[].Instances[].{Id:InstanceId,State:State.Name,IP:PublicIpAddress}' `
  --output table
```

Anotá la **IP pública nueva** de `repuestossur-ia` (`i-083d6ec1a6e00ca33`).
Al 2026-11-25 estaba en **`34.201.171.124`**; no la des actualices a mano:
consultala siempre con `describe-instances` porque cambia al reiniciar el lab.
Si aparece `stopped`:

```powershell
aws ec2 start-instances --instance-ids i-083d6ec1a6e00ca33 --profile repuestos --region us-east-1
aws ec2 wait instance-running --instance-ids i-083d6ec1a6e00ca33 --profile repuestos --region us-east-1
```

### 3. Actualizar la regla SSH del Security Group

El SG es `sg-0e3b80ab3a61837a3` (verificá con `aws ec2 describe-security-groups`).
Reemplazá `IP_VIEJA` por la IP que tenías antes y `IP_NUEVA` por `$miIp`:

```powershell
aws ec2 revoke-security-group-ingress --group-id sg-0e3b80ab3a61837a3 `
  --protocol tcp --port 22 --cidr IP_VIEJA/32 --profile repuestos --region us-east-1

aws ec2 authorize-security-group-ingress --group-id sg-0e3b80ab3a61837a3 `
  --protocol tcp --port 22 --cidr IP_NUEVA/32 `
  --description 'SSH desde IP actual' --profile repuestos --region us-east-1
```

Los puertos 80 y 443 ya están abiertos a `0.0.0.0/0`; no los toques.
El puerto 8000 **nunca** se expone.

### 4. Clave PEM y acceso SSH

Descargá el PEM del lab (**Download PEM**) y guardalo fuera del repo. Si es el
mismo par `repuestossur-ia`, sirve el de siempre; si no, importalo:

```powershell
icacls "C:\ruta\IA.pem" /inheritance:r /grant:r "$($env:USERNAME):F"

ssh -i "C:\ruta\IA.pem" ec2-user@IP_NUEVA
```

Si el PEM que tenés no coincide con el par `repuestossur-ia` (o el lab te
entregó uno nuevo que no alcanza a bajar), usá **EC2 Instance Connect**: la
clave se inyecta por API y sirve por 60 segundos.

```powershell
# 1) clave temporal local
$key = "$env:TEMP\opencode\repuestossur_deploy.pem"
ssh-keygen -t rsa -b 2048 -f $key -N '""' -q
$pub = (Get-Content "$key.pub" -Raw).Trim()

# 2) inyectar (repetir antes de cada ssh porque expira)
$az = aws ec2 describe-instances --instance-ids i-083d6ec1a6e00ca33 `
  --query 'Reservations[0].Instances[0].Placement.AvailabilityZone' --output text
aws ec2-instance-connect send-ssh-public-key `
  --instance-id i-083d6ec1a6e00ca33 --instance-os-user ec2-user `
  --availability-zone $az --ssh-public-key $pub

# 3) entrar
ssh -i $key ec2-user@IP_NUEVA
```

Acordate de actualizar primero la regla SSH del SG con tu IP actual (paso 3).

## 4b. Variables de auth después de un `git pull`

El `.env` del servidor ya tiene estas claves; si faltan, agregarlas **sin
imprimir la password** y con `chmod 600 .env`:

```env
ADMIN_USER="admin"
ADMIN_PASSWORD="<password elegida; solo en el .env del servidor>"
AUTH_DB_PATH="data/internal/auth.db"
WEB_SESSION_TTL_S="28800"
LOGIN_MAX_ATTEMPTS="5"
LOGIN_LOCKOUT_S="900"
REGISTER_MAX_PER_HOUR="50"
AUDIT_RETENTION_DAYS="30"
MAX_CONCURRENT_CHATS="3"
CHAT_QUEUE_WAIT_S="15"
CHAT_RATE_LIMIT_PER_MIN="20"
WEB_RETRY_WAIT_S="5"
AGENT_CIRCUIT_THRESHOLD="3"
AGENT_CIRCUIT_COOLDOWN_S="30"
REPUSTOS_HTTPS="1"
REPUSTOS_ALLOWED_ORIGIN=""
```

Ojo: si el `.env` no termina con salto de línea, la primera variable que
agregues con `>>` se concatena con la última línea y `python-dotenv` no la
lee. Agregá un `printf '\n'` antes del primer `>>` o corregí esa línea.

Dentro del servidor:

```bash
sudo systemctl status repuestossur nginx
curl -s http://127.0.0.1:8000/api/health
journalctl -u repuestossur -f
cd /opt/repuestossur/EvaluacionIA1 && git pull --ff-only origin main
```

Los servicios están habilitados con `systemctl enable`, así que **arrancan
solas** después del reboot.

### 5. Comprobación desde tu máquina

El servicio está en **HTTPS** con certificado autofirmado: usa `https://` y
`-k` en curl (o acepta el aviso del navegador una vez).

```powershell
curl.exe -sk https://IP_NUEVA/api/health
curl.exe -sk -o NUL -w 'HTTP %{http_code}\n' https://IP_NUEVA/

[System.Net.ServicePointManager]::ServerCertificateValidationCallback = {$true}
$body = [Text.Encoding]::UTF8.GetBytes('{"message":"¿Qué alternador recomiendas para Suzuki Swift 2014?","session":"check"}')
Invoke-RestMethod -Uri 'https://IP_NUEVA/api/chat' -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 180 |
  Select-Object respuesta, used_llm, modelo, reintentos | ConvertTo-Json -Depth 5
```

Esperado: `llm_disponible: true`, 12 repuestos, 3 manuales + 12 filas en
Chroma, y una respuesta citando `ALT-01` / `manual_alternador.pdf`.

### 6. Si `/api/health` dice `llm_disponible: false`

En el servidor:

```bash
cd /opt/repuestossur/EvaluacionIA1
grep -E '^(LLM_PROVIDER|GROQ_MODEL|EMAIL_MODE)=' .env   # no imprimas la key
sudo systemctl restart repuestossur
.venv/bin/python scripts/verify_env.py
```

El `.env` guarda `GROQ_API_KEY` con `chmod 600` y no viaja en git. Si la key
cambió, reescribí esa línea y reiniciá el servicio.

Si usás **LangSmith**, revisá también que `LANGSMITH_TRACING=true` y que
`LANGSMITH_API_KEY` sea la key vigente (un token viejo da `403 Forbidden` en
la API y no genera trazas). Para comprobarlo en el servidor:

```bash
grep -E '^(LANGSMITH_TRACING|LANGSMITH_PROJECT)=' .env   # sin imprimir la key
cd /opt/repuestossur/EvaluacionIA1
.venv/bin/python -c "from langsmith import Client; print([p.name for p in Client().list_projects()])"
```

Debe listar `EvaluacionIA1`. Después de una consulta al chat, deben aparecer
runs con `client.list_runs(project_name='EvaluacionIA1', limit=5)`.

### 6b. Login, roles y prueba de carga

La interfaz ya **no es pública**: abrí `http://<IP>/login`. Cualquier compañero
puede crear su cuenta en `/register` (rol `cliente`) y el admin entra con
`ADMIN_USER`/`ADMIN_PASSWORD` del `.env` (se crea una sola vez y se guarda
hasheado en `data/internal/auth.db`). El panel del admin está en `/admin`:
usuarios, sesiones activas, auditoría (30 días) e inventario.

Variables nuevas del `.env` (ver `.env.example`):
`AUTH_DB_PATH`, `WEB_SESSION_TTL_S`, `LOGIN_MAX_ATTEMPTS`, `LOGIN_LOCKOUT_S`,
`REGISTER_MAX_PER_HOUR`, `AUDIT_RETENTION_DAYS`, `MAX_CONCURRENT_CHATS`,
`CHAT_QUEUE_WAIT_S`, `CHAT_RATE_LIMIT_PER_MIN`, `WEB_RETRY_WAIT_S`,
`AGENT_CIRCUIT_THRESHOLD`,
`AGENT_CIRCUIT_COOLDOWN_S`, `REPUSTOS_HTTPS` y `REPUSTOS_ALLOWED_ORIGIN`.

Para verificar después de un `git pull` + restart:

```bash
cd /opt/repuestossur/EvaluacionIA1
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/api/health   # 200
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/api/inventory # 401
.venv/bin/python scripts/load_test.py --url http://127.0.0.1:8000 \
  --users 5 --requests 1 --admin-user "$ADMIN_USER" --admin-password "$ADMIN_PASSWORD"
```

El load test deja el informe en `tests/resultados/load/load_test.json` y debe
dar `ok: true`, sin 5xx, con `cliente_inventory: 403` y `admin_inventory: 200`.
Si hay 503, bajá `--users` o subí `MAX_CONCURRENT_CHATS` con cuidado (el cupo
gratuito de Groq es por modelo).

### 7. Si la instancia fue terminada (ya no aparece en `describe-instances`)

Ahí sí hay que desplegar desde cero. Seguí **`deploy/README_AWS.md`**, con el
punto clave: **Python 3.12 + `torch==2.14.1` desde el índice CPU antes de
`pip install -r requirements.txt`**, y después `ingestion/ingest.py`,
systemd, Nginx y el `.env`.

## Recordatorio

Al cerrar el lab se vencen las credenciales y conviene rotarlas. Nunca subas
`.env`, `chroma_db/`, `logs/` ni la PEM al repositorio.
