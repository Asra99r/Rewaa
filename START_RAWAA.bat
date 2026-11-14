@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
 echo Python Launcher (py) not found. Install Python 3.11+ and try again.
 pause
 exit /b 1
)
if not exist .venv\Scripts\python.exe (
 echo Setting up local virtual environment...
 py -m venv .venv
)
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 ( pause & exit /b 1 )
if not exist .env copy .env.example .env >nul
echo Open this URL in your browser: http://127.0.0.1:8000
.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000 --env-file .env
pause
