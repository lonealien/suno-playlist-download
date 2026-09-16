@echo off
rem ===============================================================
rem  Suno Playlist Downloader - Iniciador automatico (Windows)
rem  ---------------------------------------------------------------
rem  Este .bat:
rem   1) Detecta se o Python esta instalado
rem   2) Se nao estiver, baixa e instala silenciosamente
rem   3) Instala as dependencias (requests, rich, pycryptodome)
rem   4) Executa o download_suno.py
rem
rem  Basta dar duplo-clique. Coloque este arquivo na MESMA pasta
rem  do download_suno.py.
rem ===============================================================

setlocal EnableExtensions
cd /d "%~dp0"
set PYTHONUTF8=1
set SUNODL_NO_PAUSE=1
chcp 65001 >nul 2>nul

echo.
echo ==============================================================
echo   SUNO PLAYLIST DOWNLOADER - Inicializador
echo ==============================================================
echo   Pasta atual: %cd%
echo ==============================================================
echo.

set "PY_VER=3.12.7"
set "PY_URL=https://www.python.org/ftp/python/%PY_VER%/python-%PY_VER%-amd64.exe"
set "PY_INSTALLER=%TEMP%\python-%PY_VER%-amd64.exe"

rem ================================================================
rem  PASSO 1 - Procurar Python ja instalado
rem ================================================================
set "PY="

where py >nul 2>nul
if not errorlevel 1 set "PY=py -3"

if not defined PY (
    where python >nul 2>nul
    if not errorlevel 1 set "PY=python"
)

if not defined PY (
    if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
        set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    )
)
if not defined PY (
    if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
        set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    )
)

if defined PY (
    echo  [OK] Python encontrado: %PY%
    goto :instalar_deps
)

rem ================================================================
rem  PASSO 2 - Python nao encontrado: baixar e instalar silenciosamente
rem ================================================================
echo  [i] Python nao encontrado neste computador.
echo      Vou baixar e instalar automaticamente (so nesta 1a vez).
echo      Download: Python %PY_VER%  ^(64 bits^)
echo.

echo  [..] Baixando o instalador oficial do python.org...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%PY_URL%' -OutFile '%PY_INSTALLER%' -UseBasicParsing } catch { Write-Host $_.Exception.Message; exit 1 }"

if errorlevel 1 (
    echo.
    echo  [X] Falha ao baixar o Python.
    echo      Verifique sua conexao com a internet ou baixe manualmente em:
    echo         https://www.python.org/downloads/windows/
    echo      Marque a opcao "Add python.exe to PATH" durante a instalacao.
    echo.
    pause
    exit /b 1
)

if not exist "%PY_INSTALLER%" (
    echo.
    echo  [X] O instalador nao foi salvo corretamente. Abortando.
    pause
    exit /b 1
)

echo  [..] Instalando Python silenciosamente ^(pode levar 1-3 minutos^)...
echo       Aguarde, nao feche esta janela.
echo.

"%PY_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_pip=1 Include_launcher=1

if errorlevel 1 (
    echo.
    echo  [X] A instalacao silenciosa falhou. Tentando modo interativo...
    echo      ^(vai abrir a janela do instalador - clique Next/Avancar^)
    "%PY_INSTALLER%"
)

del "%PY_INSTALLER%" >nul 2>nul

set "PY="
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
)
if not defined PY (
    if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
        set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    )
)
if not defined PY (
    if exist "%LOCALAPPDATA%\Programs\Python\Python310\python.exe" (
        set "PY=%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    )
)

if not defined PY (
    echo.
    echo  [X] Python foi instalado mas nao consegui localiza-lo.
    echo      FECHE esta janela e execute este .bat novamente.
    echo.
    pause
    exit /b 1
)

echo.
echo  [OK] Python instalado com sucesso em:
echo       %PY%
echo.

rem ================================================================
rem  PASSO 3 - Instalar / verificar dependencias (pycryptodome!)
rem ================================================================
:instalar_deps
echo  [..] Verificando dependencias (requests, rich, pycryptodome)...
%PY% -c "import requests, rich, Crypto" >nul 2>nul
if not errorlevel 1 (
    echo  [OK] Todas as dependencias ja estao instaladas.
    goto :executar
)

echo  [..] Instalando dependencias, aguarde...
%PY% -m pip install --user --quiet --disable-pip-version-check --no-warn-script-location requests rich pycryptodome

if errorlevel 1 (
    echo  [!] Primeira tentativa falhou. Atualizando pip e tentando de novo...
    %PY% -m pip install --user --quiet --upgrade pip
    %PY% -m pip install --user --disable-pip-version-check requests rich pycryptodome
)

%PY% -c "import requests, rich, Crypto" >nul 2>nul
if errorlevel 1 (
    echo.
    echo  [X] Nao foi possivel instalar as dependencias.
    echo      Verifique sua conexao com a internet e tente de novo.
    echo.
    pause
    exit /b 1
)

echo  [OK] Dependencias instaladas.
echo.

rem ================================================================
rem  PASSO 4 - Executar o script
rem ================================================================
:executar
if not exist "%~dp0download_suno.py" (
    echo.
    echo  [X] Arquivo 'download_suno.py' nao encontrado nesta pasta:
    echo      %~dp0
    echo.
    echo      Coloque este .bat na MESMA pasta que o download_suno.py.
    echo.
    pause
    exit /b 1
)

echo ==============================================================
echo   Tudo pronto! Iniciando o Suno Downloader...
echo ==============================================================
echo.

%PY% "%~dp0download_suno.py" %*

echo.
echo  ----- Execucao encerrada -----
echo.
pause
endlocal