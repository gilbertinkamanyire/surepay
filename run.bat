@echo off
REM ===================================================================
REM  SurePay Learn - Windows launcher
REM  Creates a virtual environment, installs dependencies, and starts
REM  the app at http://127.0.0.1:5000
REM ===================================================================
setlocal
cd /d "%~dp0"

if not exist ".venv" (
    echo Creating virtual environment...
    py -3 -m venv .venv 2>NUL || python -m venv .venv
)

call ".venv\Scripts\activate.bat"

echo Installing dependencies...
python -m pip install --upgrade pip
pip install -r requirements.txt

echo.
echo Starting SurePay Learn at http://127.0.0.1:5000  (press CTRL+C to stop)
echo.
python app.py

endlocal
