@echo off
title Visao Computacional com IA Local
cd /d "%~dp0"
call scripts\ambiente.bat || goto erro
echo Iniciando a demonstracao (funciona sem internet)...
call scripts\subir.bat --pull never || goto erro
call scripts\aguardar.bat || goto erro
echo.
echo Para encerrar, rode 3-parar.bat
timeout /t 5 >nul
exit /b 0
:erro
echo.
echo [ERRO] Nao foi possivel iniciar. Se for o primeiro uso, rode antes 1-preparar.bat (com internet).
pause
exit /b 1
