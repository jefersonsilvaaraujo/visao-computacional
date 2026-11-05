@echo off
title Preparacao - Visao Computacional com IA Local
cd /d "%~dp0"
echo ==============================================================
echo  PREPARACAO (precisa de internet - execute apenas uma vez)
echo  Baixa as imagens, os pesos do detector YOLO e a LLM local.
echo ==============================================================
call scripts\ambiente.bat || goto erro
echo.
echo [1/3] Construindo a imagem da aplicacao (pode levar varios minutos)...
docker compose %ARQS_CPU% build || goto erro
echo.
echo [2/3] Iniciando os containers...
call scripts\subir.bat || goto erro
echo.
echo [3/3] Baixando o modelo de linguagem %LLM_MODELO% (cerca de 2 GB)...
docker compose exec ollama ollama pull %LLM_MODELO% || goto erro
call scripts\aguardar.bat
echo.
echo Preparacao concluida! A partir de agora a aplicacao funciona SEM internet.
echo Para os proximos usos, rode 2-iniciar.bat
pause
exit /b 0
:erro
echo.
echo [ERRO] A preparacao nao terminou. Verifique a internet e se o Docker Desktop esta aberto.
pause
exit /b 1
