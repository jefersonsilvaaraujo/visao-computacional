@echo off
rem Sobe os containers, usando a GPU NVIDIA quando disponivel (nao execute diretamente).
rem Uso: call scripts\subir.bat [opcoes extras do "docker compose up"]
if "%GPU%"=="1" (
  echo GPU NVIDIA encontrada: a LLM vai usar a GPU.
  docker compose %ARQS% up -d %*
  if not errorlevel 1 exit /b 0
  echo.
  echo [AVISO] Nao foi possivel usar a GPU dentro do Docker. Iniciando em modo CPU...
  echo         ^(Atualize o driver NVIDIA e confirme que o Docker Desktop usa WSL 2.^)
  echo.
)
docker compose %ARQS_CPU% up -d %*
exit /b %errorlevel%
