@echo off
cd /d "%~dp0"

:: Se o ambiente virtual não existir, cria e instala dependências automaticamente
if not exist ".\.venv\Scripts\pythonw.exe" (
    echo ==========================================================
    echo  EyeControl - Primeira Inicializacao Detectada
    echo ==========================================================
    echo  Criando ambiente virtual (.venv) e instalando dependencias...
    echo  Isso pode levar alguns instantes na primeira execucao.
    echo.
    python -m venv .venv
    if errorlevel 1 (
        echo [ERRO] Python nao foi encontrado no sistema ou falhou ao criar a venv.
        echo Certifique-se de ter o Python 3.10+ instalado e no PATH do Windows.
        pause
        exit /b 1
    )
    .\.venv\Scripts\python.exe -m pip install --upgrade pip
    .\.venv\Scripts\pip.exe install -r requirements.txt
    if errorlevel 1 (
        echo [ERRO] Falha ao instalar dependencias do requirements.txt.
        pause
        exit /b 1
    )
    echo.
    echo [OK] Ambiente configurado com sucesso!
    echo.
)

:: Executa o EyeControl sem manter janela de prompt presa
start "" ".\.venv\Scripts\pythonw.exe" -m src.main
