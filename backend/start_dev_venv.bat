@echo off
echo Activating Virtual Environment...
call venv\Scripts\activate
REM Use venv Python explicitly so Windows Store Python doesn't take precedence
set VENV_PYTHON=%~dp0venv\Scripts\python.exe
"%VENV_PYTHON%" --version
echo Virtual environment activated

echo Starting EyeReadDemo v7 Backend...
echo Backend will be available at: http://localhost:8080
echo WebSocket endpoint: ws://localhost:8080/ws/{client_id}
echo API docs: http://localhost:8080/docs
echo Health check: http://localhost:8080/health
echo Eye tracking: Real hardware mode only
echo.
echo ==================================================

cd /d "%~dp0src"
"%VENV_PYTHON%" main.py
