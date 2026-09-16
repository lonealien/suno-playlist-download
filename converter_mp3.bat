@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul 2>nul
title Conversor M4A - MP3

rem ===============================================================
rem  CONVERSOR M4A -^> MP3 by: LONE ALIEN
rem  ---------------------------------------------------------------
rem  Lista as playlists dentro de "Playlists", deixa escolher qual
rem  converter para MP3 e APAGA os .m4a apos conversao bem-sucedida.
rem ===============================================================

cls
echo ==============================================================
echo    CONVERSOR M4A  ^>  MP3
echo ==============================================================
echo.

rem ---------- Verifica ffmpeg ----------
where ffmpeg >nul 2>nul
if not errorlevel 1 goto :ffmpeg_ok

if exist "%LOCALAPPDATA%\ffmpeg\bin\ffmpeg.exe" (
    set "PATH=%LOCALAPPDATA%\ffmpeg\bin;%PATH%"
    echo  [OK] ffmpeg encontrado em: %LOCALAPPDATA%\ffmpeg\bin
    goto :after_ffmpeg
)

echo  [X] ffmpeg nao encontrado.
echo.
echo      Baixe em: https://www.gyan.dev/ffmpeg/builds/
echo.
pause
exit /b 1

:ffmpeg_ok
echo  [OK] ffmpeg disponivel no PATH.

:after_ffmpeg
echo.

rem ---------- Pasta raiz ----------
set "RAIZ=%~1"
if defined RAIZ goto :verificar_raiz

:perguntar_raiz
set "RAIZ="
echo Cole o caminho da pasta onde esta a pasta "Playlists".
echo (ou arraste a pasta para dentro desta janela e aperte ENTER)
echo.
set /p "RAIZ=> "

:verificar_raiz
if not defined RAIZ goto :perguntar_raiz
set "RAIZ=%RAIZ:"=%"

if not exist "%RAIZ%\" (
    echo.
    echo  [!] Pasta nao existe: "%RAIZ%"
    echo.
    goto :perguntar_raiz
)

rem ---- Descobre onde estao as playlists ----
set "PASTA_PLAYLISTS="
if exist "%RAIZ%\Playlists\" set "PASTA_PLAYLISTS=%RAIZ%\Playlists"
if defined PASTA_PLAYLISTS goto :pasta_ok

for %%D in ("%RAIZ%") do (
    if /I "%%~nxD"=="Playlists" set "PASTA_PLAYLISTS=%RAIZ%"
)
if not defined PASTA_PLAYLISTS goto :pasta_erro
goto :pasta_ok

:pasta_erro
echo.
echo  [!] Nao encontrei a pasta "Playlists" dentro de: %RAIZ%
echo.
goto :perguntar_raiz

:pasta_ok

rem ---------- Lista playlists ----------
:listar
cls
echo ==============================================================
echo    CONVERSOR M4A  ^>  MP3
echo ==============================================================
echo.
echo Pasta base:
echo   %PASTA_PLAYLISTS%
echo.
echo Playlists disponiveis:
echo.

set "TMPLIST=%TEMP%\suno_pl_list_%RANDOM%%RANDOM%.txt"
dir /b /ad "%PASTA_PLAYLISTS%" > "%TMPLIST%" 2>nul

set "count=0"
for /f "usebackq delims=" %%D in ("%TMPLIST%") do (
    set /a count+=1
    rem *** guarda o CAMINHO COMPLETO, nao apenas o nome ***
    set "PL[!count!]=%PASTA_PLAYLISTS%\%%D"
    echo   [!count!]  %%D
)

if not defined count goto :sem_playlists
if "!count!"=="0" goto :sem_playlists

echo.
echo   [T]  Converter TODAS as playlists acima
echo   [V]  Voltar e escolher outra pasta raiz
echo.
echo   NOTA: os arquivos .m4a serao APAGADOS apos a conversao.
echo.
set "ESCOLHA="
set /p "ESCOLHA=Escolha o numero da playlist (T=todas, V=voltar): "

if not defined ESCOLHA goto :listar

if /I "%ESCOLHA%"=="V" goto :voltar_raiz
if /I "%ESCOLHA%"=="T" goto :converter_todas

set "SEL=!PL[%ESCOLHA%]!"
if not defined SEL goto :invalido

call :converter "%SEL%"
goto :fim

:converter_todas
for /L %%N in (1,1,!count!) do (
    call :converter "!PL[%%N]!"
)
goto :fim

:invalido
echo.
echo  [!] Opcao invalida: %ESCOLHA%
echo.
pause
goto :listar

:voltar_raiz
if exist "%TMPLIST%" del "%TMPLIST%" >nul 2>nul
goto :perguntar_raiz

:sem_playlists
echo   *** nenhuma subpasta encontrada ***
if exist "%TMPLIST%" del "%TMPLIST%" >nul 2>nul
echo.
pause
exit /b 1

:fim
if exist "%TMPLIST%" del "%TMPLIST%" >nul 2>nul
echo.
echo ==============================================================
echo    Concluido!
echo ==============================================================
echo.
pause
exit /b 0


rem ==============================================================
rem  Sub-rotina: converte todos os .m4a de uma pasta para .mp3
rem  e APAGA os .m4a apos conversao bem-sucedida.
rem ==============================================================
:converter
set "PASTA=%~1"
set "PASTA=%PASTA:"=%"

echo.
echo --------------------------------------------------------------
echo Convertendo: %~nx1
echo Pasta:       %PASTA%
echo --------------------------------------------------------------

set "tem=0"
for %%F in ("%PASTA%\*.m4a") do set "tem=1"
if "%tem%"=="0" (
    echo   [i] Nenhum arquivo .m4a nesta pasta. Pulando.
    exit /b 0
)

set "conv=0"
set "skip=0"
set "fail=0"

for %%F in ("%PASTA%\*.m4a") do (
    if exist "%%~dpnF.mp3" (
        del "%%F" >nul 2>nul
        set /a skip+=1
        echo   [=] ja existia MP3 - apagando m4a: %%~nF
    ) else (
        echo   [>] convertendo: %%~nxF
        ffmpeg -y -loglevel error -i "%%F" -codec:a libmp3lame -q:a 5 -threads 0 "%%~dpnF.mp3"
        if exist "%%~dpnF.mp3" (
            del "%%F" >nul 2>nul
            set /a conv+=1
        ) else (
            set /a fail+=1
            echo       [X] falhou - o m4a foi mantido: %%~nxF
        )
    )
)

echo.
echo   Resultado: !conv! convertidas  ^|  !skip! ja existiam  ^|  !fail! falhas
exit /b 0