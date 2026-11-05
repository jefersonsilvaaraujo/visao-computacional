#!/usr/bin/env bash
source "$(dirname "$0")/scripts/comum.sh"
echo "Iniciando a demonstração (funciona sem internet)..."
subir --pull never || { echo "[ERRO] Se for o primeiro uso, rode antes ./1-preparar.sh (com internet)."; exit 1; }
aguardar
echo "Para encerrar: ./3-parar.sh"
