#!/usr/bin/env bash
# PREPARAÇÃO (precisa de internet, apenas uma vez)
source "$(dirname "$0")/scripts/comum.sh"
echo "[1/3] Construindo a imagem da aplicação (pode levar vários minutos)..."
docker compose "${ARQS_CPU[@]}" build
echo "[2/3] Iniciando os containers..."
subir
echo "[3/3] Baixando o modelo de linguagem ${LLM_MODELO} (cerca de 2 GB)..."
docker compose exec ollama ollama pull "${LLM_MODELO}"
aguardar
echo; echo "Preparação concluída! A partir de agora a aplicação funciona SEM internet. Próximos usos: ./2-iniciar.sh"
