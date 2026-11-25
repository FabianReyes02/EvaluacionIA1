#!/usr/bin/env bash
# Certificado autofirmado para la IP pública mientras no haya dominio con ACME.
# Uso: bash deploy/generar_certificado_autofirmado.sh [IP_PUBLICA]
set -euo pipefail

IP="${1:-34.201.171.124}"
DIR="/etc/nginx/ssl"
ARCHIVO_CRT="$DIR/repuestossur.crt"
ARCHIVO_KEY="$DIR/repuestossur.key"

sudo mkdir -p "$DIR"
sudo openssl req -x509 -nodes -newkey rsa:2048 -days 365 \
  -subj "/CN=$IP" \
  -addext "subjectAltName=IP:$IP,DNS:localhost" \
  -keyout "$ARCHIVO_KEY" -out "$ARCHIVO_CRT"

sudo chmod 600 "$ARCHIVO_KEY"
sudo chmod 644 "$ARCHIVO_CRT"
echo "Certificado generado en $ARCHIVO_CRT (el navegador avisará que es autofirmado)."
