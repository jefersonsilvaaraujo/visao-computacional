#!/usr/bin/env bash
# Funções comuns aos scripts de macOS/Linux (não execute diretamente).
set -euo pipefail
cd "$(dirname "$0")"
PORTA=8080
LLM_MODELO="llama3.2:3b"
if [ -f .env ]; then
  PORTA=$(grep -E '^PORTA=' .env | tail -1 | cut -d= -f2- || echo 8080); PORTA=${PORTA:-8080}
  LLM_MODELO=$(grep -E '^LLM_MODELO=' .env | tail -1 | cut -d= -f2- || echo llama3.2:3b); LLM_MODELO=${LLM_MODELO:-llama3.2:3b}
fi
ARQS_CPU=(-f docker-compose.yml)
if ! docker info >/dev/null 2>&1; then
  echo; echo "[ERRO] O Docker não está em execução. Abra o Docker Desktop e tente novamente."; exit 1
fi

subir() {
  if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
    echo "GPU NVIDIA encontrada: a LLM vai usar a GPU."
    if docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d "$@"; then return 0; fi
    echo "[AVISO] Não foi possível usar a GPU no Docker (instale o NVIDIA Container Toolkit). Usando CPU..."
  fi
  docker compose "${ARQS_CPU[@]}" up -d "$@"
}

aguardar() {
  echo "Aguardando a aplicação ficar pronta..."
  for _ in $(seq 1 90); do
    if curl -fs "http://localhost:${PORTA}/api/status" >/dev/null 2>&1; then
      echo; echo "Aplicação pronta em http://localhost:${PORTA}"
      (command -v open >/dev/null && open "http://localhost:${PORTA}") || (command -v xdg-open >/dev/null && xdg-open "http://localhost:${PORTA}") || true
      return 0
    fi
    sleep 2
  done
  echo "[ERRO] A aplicação não respondeu. Veja: docker compose logs app"; return 1
}
