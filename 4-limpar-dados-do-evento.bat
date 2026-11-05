@echo off
cd /d "%~dp0"
echo Apaga os logs tecnicos (RNF09). Os modelos baixados e os ajustes NAO sao apagados.
choice /m "Confirmar"
if errorlevel 2 exit /b 0
docker compose run --rm --no-deps app sh -c "rm -f /app/logs/*" && echo Logs tecnicos apagados.
echo.
echo Os objetos que a IA aprendeu com os visitantes ficam guardados para as proximas demonstracoes.
choice /m "Apagar tambem o que foi aprendido"
if errorlevel 2 goto fim
docker compose run --rm --no-deps app sh -c "rm -f /app/dados/aprendizado*" && echo Aprendizado apagado.
:fim
pause
