@echo off
cd /d "%~dp0"
title ImportX - Robo Onuh V3
echo ============================================
echo  IMPORTX ATACADO - ROBO DA ONUH - V3
echo  Pasta: %CD%
echo ============================================
echo.
where py >nul 2>&1
if %errorlevel%==0 (set PY=py) else (set PY=python)
echo Usando: %PY%
echo.
echo [1/3] Instalando biblioteca...
%PY% -m pip install --upgrade pip
%PY% -m pip install playwright
echo.
echo [2/3] Instalando navegador do robo...
%PY% -m playwright install chromium
echo.
echo [3/3] Abrindo site da Onuh para voce logar...
echo Faca login normal, depois volte aqui e aperte ENTER
%PY% salvar_login.py
echo.
echo ============================================
echo  Se aparecer onuh_cookies.json na pasta, DEU CERTO!
echo ============================================
dir onuh_cookies.json
pause
