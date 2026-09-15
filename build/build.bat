@echo off
REM Builds dist\GlucoPop.exe (portable) and dist\GlucoPop-Setup-x.y.z.exe (installer, needs Inno Setup 6)
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
echo Portable exe: dist\GlucoPop.exe
set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist %ISCC% (
  %ISCC% build\installer.iss && echo Installer: dist\GlucoPop-Setup-*.exe
) else (
  echo Inno Setup 6 not found - installer skipped. Get it from https://jrsoftware.org/isdl.php
)
pause
