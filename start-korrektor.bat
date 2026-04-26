@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "VENV_PYW=%SCRIPT_DIR%.venv\Scripts\pythonw.exe"
set "ENTRY=%SCRIPT_DIR%korrektor.py"

if not exist "%ENTRY%" (
  echo Startdatei nicht gefunden: %ENTRY%
  pause
  exit /b 1
)

if exist "%VENV_PYW%" (
  start "" "%VENV_PYW%" "%ENTRY%"
) else (
  start "" pyw -3 "%ENTRY%"
)

endlocal
