@echo off
cd /d "%~dp0"
echo Encerrando a demonstracao...
docker compose down
echo Pronto. Os modelos continuam salvos para o proximo uso.
timeout /t 3 >nul
