@echo off
setlocal EnableExtensions

REM ------------------------------------------------------------
REM Script: scripts/run.bat
REM Purpose: Check Python/pip, install dependencies, run app.
REM Project root: parent of this scripts\ folder (portable; no absolute paths).
REM ------------------------------------------------------------

cd /d "%~dp0.."

set "SCRIPT=main.py"
set "REQUIREMENTS=requirements.txt"
set "PYTHON_EXE="
set "PYTHON_ARGS="

if not exist "%SCRIPT%" (
    echo [ERROR] Could not find "%SCRIPT%" in:
    echo         %cd%
    exit /b 1
)

where py >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set "PYTHON_EXE=py"
    set "PYTHON_ARGS=-3"
) else (
    where python >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        set "PYTHON_EXE=python"
    ) else (
        where python3 >nul 2>&1
        if %ERRORLEVEL% EQU 0 (
            set "PYTHON_EXE=python3"
        )
    )
)

if "%PYTHON_EXE%"=="" (
    echo [ERROR] Python was not found.
    echo         Install Python 3 and try again.
    exit /b 1
)

%PYTHON_EXE% %PYTHON_ARGS% --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python command exists but cannot run correctly.
    exit /b 1
)

%PYTHON_EXE% %PYTHON_ARGS% -m pip --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [INFO] pip not found. Trying to install pip with ensurepip...
    %PYTHON_EXE% %PYTHON_ARGS% -m ensurepip --upgrade
    if %ERRORLEVEL% NEQ 0 (
        echo [ERROR] Could not install pip automatically.
        exit /b 1
    )
)

if exist "%REQUIREMENTS%" (
    echo [INFO] Installing/updating dependencies from "%REQUIREMENTS%"...
    %PYTHON_EXE% %PYTHON_ARGS% -m pip install -r "%REQUIREMENTS%"
    if %ERRORLEVEL% NEQ 0 (
        echo [ERROR] Dependency installation failed.
        exit /b 1
    )
) else (
    echo [INFO] No "%REQUIREMENTS%" file found. Skipping dependency install.
)

echo [INFO] Starting %SCRIPT%...
%PYTHON_EXE% %PYTHON_ARGS% "%SCRIPT%"
exit /b %ERRORLEVEL%
