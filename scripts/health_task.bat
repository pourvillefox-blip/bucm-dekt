@echo off
chcp 65001 >nul
cd /d "%~dp0.."
if not exist "logs" mkdir "logs"
set "PY=C:\Users\Fox\AppData\Local\Programs\Python\Python312\python.exe"
if not exist "%PY%" (
  echo %date% %time% python not found: %PY% >> "logs\health_task.log"
  exit /b 1
)
"%PY%" -X utf8 "scripts\healthcheck.py" >> "logs\health_task.log" 2>&1
