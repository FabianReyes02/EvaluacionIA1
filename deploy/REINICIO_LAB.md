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

```powershell
curl.exe -s http://IP_NUEVA/api/health
curl.exe -s -o NUL -w 'HTTP %{http_code}\n' http://IP_NUEVA/

$body = [Text.Encoding]::UTF8.GetBytes('{"message":"¿Qué alternador recomiendas para Suzuki Swift 2014?","session":"check"}')
Invoke-RestMethod -Uri 'http://IP_NUEVA/api/chat' -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 180 |
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

### 7. Si la instancia fue terminada (ya no aparece en `describe-instances`)

Ahí sí hay que desplegar desde cero. Seguí **`deploy/README_AWS.md`**, con el
punto clave: **Python 3.12 + `torch==2.14.1` desde el índice CPU antes de
`pip install -r requirements.txt`**, y después `ingestion/ingest.py`,
systemd, Nginx y el `.env`.

## Recordatorio

Al cerrar el lab se vencen las credenciales y conviene rotarlas. Nunca subas
`.env`, `chroma_db/`, `logs/` ni la PEM al repositorio.
