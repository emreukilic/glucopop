@echo off
REM Builds dist\GlucoPop.exe  (run from anywhere; needs Python 3.10+ on PATH)
setlocal
cd /d "%~dp0\.."
if not exist .venv (
  python -m venv .venv || (echo Python not found. Install from python.org and tick "Add to PATH". & pause & exit /b 1)
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements-build.txt
python assets\make_icon.py
pyinstaller --noconfirm --clean --distpath dist --workpath build\work build\glucopop.spec
if errorlevel 1 (echo BUILD FAILED & pause & exit /b 1)
echo.
echo Done: dist\GlucoPop.exe
pause
