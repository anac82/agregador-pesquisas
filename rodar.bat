@echo off
REM Botão "Rodar" — duplo-clique para executar o agregador.
REM Gera o Excel atualizado e abre automaticamente.

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERRO] Ambiente nao configurado.
    echo Por favor, rode "instalar.bat" primeiro.
    echo.
    pause
    exit /b 1
)

.venv\Scripts\python.exe -m scrapers.main
if errorlevel 1 (
    echo.
    echo [ERRO] Algo deu errado durante a execucao.
    pause
    exit /b 1
)

echo.
echo Abrindo o Excel...
start "" "output\agregador_pesquisas.xlsx"

echo.
pause
