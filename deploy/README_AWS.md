# Deploy en AWS (recomendado: EC2 Amazon Linux 2023 / Ubuntu)

Opción elegida por defecto: **EC2** detrás de **Nginx** (reverse proxy), servicio **systemd**. No expongas el puerto 8000 a internet; abre solo 80/443 en el Security Group.

## 1) Preparar la instancia
- AMI: Amazon Linux 2023 o Ubuntu 22.04+.
- Security Group (inbound): SSH **solo tu IP** (o usa **SSM Session Manager** y no abras SSH) + HTTP 80 (y 443 si usas TLS).
- Usuario sugerido: `ec2-user` (AL2023) o `ubuntu` (Ubuntu).

## 2) Instalar dependencias del sistema (ejemplo Ubuntu)

```bash
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3-pip nginx git
```

En Amazon Linux 2023:

```bash
sudo dnf install -y python3.11 python3.11-pip git nginx
```

(Ajusta el nombre del paquete de Python al que tengas disponible.)

## 3) Copiar el proyecto

Opción A (git): clona el repo en `/opt/repuestossur` y entra en `EvaluacionIA1`.

Opción B (zip): sube el código sin `.env`, sin `chroma_db/`, sin `logs/`, sin `data/memory/*.jsonl`, sin `data/exports/`, sin `data/internal/tienda*.db*` (ya están en `.gitignore`).

```bash
sudo mkdir -p /opt/repuestossur
sudo chown $USER:$USER /opt/repuestossur
cd /opt/repuestossur
# git clone ... EvaluacionIA1
cd EvaluacionIA1
python3.12 -m venv .venv   # o python3.11
source .venv/bin/activate
pip install -r requirements.txt
```

## 4) Variables de entorno (`.env`)

En el servidor, crea `.env` en la raíz del proyecto (no en git). Mínimo:

```env
LLM_PROVIDER="groq"
GROQ_API_KEY="gsk_..."
GROQ_MODEL="qwen/qwen3.8-27b"
REPUSTOS_HOST="127.0.0.1"
REPUSTOS_PORT="8000"
```

Ajusta `EMAIL_*`, `TIENDA_DB_PATH`, etc. según necesites. Permisos: `chmod 600 .env`.

## 5) Datos e índice RAG

Si usas `data/internal/inventory.csv` y manuales en `data/external/manuales/`, desde la raíz del proyecto:

```bash
source .venv/bin/activate
python ingestion/ingest.py
```

## 6) systemd

Copia el archivo de ejemplo:

```bash
sudo cp deploy/repuestossur.service /etc/systemd/system/repuestossur.service
sudo systemctl daemon-reload
sudo systemctl enable repuestossur
sudo systemctl start repuestossur
sudo systemctl status repuestossur
```

Si tu ruta o usuario son distintos, edita `/etc/systemd/system/repuestossur.service` (WorkingDirectory, ExecStart, User/Group).

## 7) Nginx

```bash
sudo cp deploy/nginx-repuestossur.conf /etc/nginx/conf.d/repuestossur.conf
# opcional: quitar default si choca
sudo nginx -t
sudo systemctl enable nginx
sudo systemctl restart nginx
```

## 8) TLS (recomendado)

Usa **Certbot** (Let’s Encrypt) o un **ALB** con ACM. Ejemplo Certbot en Ubuntu:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d tudominio.com
```

## 9) Comprobaciones

- `curl -s http://127.0.0.1:8000/api/health` en el servidor.
- Desde fuera: `http://IP_PUBLICA/` (o tu dominio).

## 10) Notas de seguridad (resumen)

- No abras 8000 en el SG; solo Nginx en 80/443.
- Secretos en `.env` con permisos 600 o en SSM/Secrets Manager (inyectarlos al arrancar el servicio).
- Logs: `journalctl -u repuestossur -f`.
- Para escalar o alta disponibilidad este diseño es mínimo; para producción seria considerar contenedores, ALB, RDS/volúmenes gestionados, etc.
