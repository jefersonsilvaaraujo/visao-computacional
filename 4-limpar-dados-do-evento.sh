#!/usr/bin/env bash
cd "$(dirname "$0")"
echo "Apaga os logs técnicos (RNF09). Os modelos baixados e os ajustes NÃO são apagados."
read -r -p "Confirmar? [s/N] " r
[[ "$r" =~ ^[sS]$ ]] || exit 0
docker compose run --rm --no-deps app sh -c "rm -f /app/logs/*" && echo "Logs técnicos apagados."
echo
echo "Os objetos que a IA aprendeu com os visitantes ficam guardados para as próximas demonstrações."
read -r -p "Apagar também o que foi aprendido? [s/N] " r
if [[ "$r" =~ ^[sS]$ ]]; then
  docker compose run --rm --no-deps app sh -c "rm -f /app/dados/aprendizado*" && echo "Aprendizado apagado."
fi
