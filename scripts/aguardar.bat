@echo off
rem Espera a interface responder e abre o navegador (nao execute diretamente).
echo Aguardando a aplicacao ficar pronta...
set /a TENTATIVAS=0
:loop
curl -fs "http://localhost:%PORTA%/api/status" >nul 2>&1
if not errorlevel 1 goto pronto
set /a TENTATIVAS+=1
if %TENTATIVAS% GEQ 90 (
  echo [ERRO] A aplicacao nao respondeu. Veja os detalhes com: docker compose logs app
  exit /b 1
)
timeout /t 2 /nobreak >nul
goto loop
:pronto
echo.
echo Aplicacao pronta em http://localhost:%PORTA%
start "" "http://localhost:%PORTA%"
exit /b 0
