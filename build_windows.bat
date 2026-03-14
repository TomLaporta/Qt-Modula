@echo off
setlocal

cd /d "%~dp0"
set "DO_STAGE=1"

for %%A in (%*) do (
    if /I "%%~A"=="--dry-run" set "DO_STAGE=0"
)

set "PY_CMD="

where py >nul 2>nul
if not errorlevel 1 (
    py -3.13 -c "import sys" >nul 2>nul && set "PY_CMD=py -3.13"
    if not defined PY_CMD py -3.12 -c "import sys" >nul 2>nul && set "PY_CMD=py -3.12"
    if not defined PY_CMD py -3.11 -c "import sys" >nul 2>nul && set "PY_CMD=py -3.11"
)

if not defined PY_CMD (
    where python >nul 2>nul
    if not errorlevel 1 set "PY_CMD=python"
)

if not defined PY_CMD (
    echo Python was not found.
    echo Install Python 3.11, 3.12, or 3.13 and make sure either py or python is available.
    exit /b 1
)

%PY_CMD% -c "import PyInstaller" >nul 2>nul
if errorlevel 1 (
    echo PyInstaller is not installed in the selected Python environment.
    echo Run: %PY_CMD% -m pip install -e ".[build]"
    exit /b 1
)

%PY_CMD% resources\scripts\build_distribution.py %*
if errorlevel 1 exit /b %errorlevel%

if "%DO_STAGE%"=="0" exit /b 0

%PY_CMD% resources\scripts\stage_distribution.py
exit /b %errorlevel%
