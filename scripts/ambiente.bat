@echo off
rem Define variaveis comuns aos scripts (nao execute diretamente).
set "PORTA=8080"
set "LLM_MODELO=llama3.2:3b"
if exist ".env" (
  for /f "usebackq eol=# tokens=1,* delims==" %%a in (".env") do (
    if /i "%%a"=="PORTA" set "PORTA=%%b"
    if /i "%%a"=="LLM_MODELO" set "LLM_MODELO=%%b"
  )
)
set "ARQS_CPU=-f docker-compose.yml"
set "ARQS=%ARQS_CPU%"
set "GPU=0"
where nvidia-smi >nul 2>&1 && nvidia-smi >nul 2>&1 && set "GPU=1"
if "%GPU%"=="1" set "ARQS=-f docker-compose.yml -f docker-compose.gpu.yml"
docker info >nul 2>&1
if errorlevel 1 (
  echo.
  echo [ERRO] O Docker nao esta em execucao.
  echo        Abra o Docker Desktop, espere aparecer "Engine running" e rode este script novamente.
  echo.
  exit /b 1
)
exit /b 0
