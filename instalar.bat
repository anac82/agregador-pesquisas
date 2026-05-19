@echo off
REM Botão "Instalar" — duplo-clique para configurar o agregador.
REM Cria um ambiente Python isolado e instala as dependências.

cd /d "%~dp0"

echo.
echo ============================================================
echo  Configurando o agregador de pesquisas...
echo ============================================================
echo.

REM Verifica se Python esta instalado
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Python nao encontrado.
    echo.
    echo Por favor, instale o Python em: https://www.python.org/downloads/
    echo IMPORTANTE: durante a instalacao, marque a opcao
    echo             "Add Python to PATH"
    echo.
    pause
    exit /b 1
)

echo [1/2] Criando ambiente virtual em .venv\
python -m venv .venv
if errorlevel 1 (
    echo [ERRO] Falha ao criar ambiente virtual.
    pause
    exit /b 1
)

echo [2/2] Instalando dependencias (pode demorar alguns minutos)...
.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
.venv\Scripts\python.exe -m pip install --quiet -r requirements.txt
if errorlevel 1 (
    echo [ERRO] Falha ao instalar dependencias.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Pronto!
echo ============================================================
echo.
echo  Para rodar o agregador, de duplo-clique em "rodar.bat"
echo.
pause
