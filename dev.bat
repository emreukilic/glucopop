@echo off
REM Run from source (no exe):  dev.bat        |  connection check:  dev.bat check
cd /d "%~dp0"
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install -q -r requirements.txt
if "%1"=="check" (python -m glucopop.check & pause) else (python -m glucopop)
