@echo off
REM Builds dist\GlucoPop\ (the program folder: GlucoPop.exe + _internal\) and
REM dist\GlucoPop-Setup-x.y.z.exe (installer, needs Inno Setup 6)
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
for /f %%v in ('python -c "import glucopop; print(glucopop.__version__)"') do set VERSION=%%v
echo.
echo Program folder: dist\GlucoPop\  (run GlucoPop.exe inside it)
set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist %ISCC% (
  %ISCC% /DAppVersion=%VERSION% build\installer.iss && echo Installer: dist\GlucoPop-Setup-%VERSION%.exe
) else (
  echo Inno Setup 6 not found - installer skipped. Get it from https://jrsoftware.org/isdl.php
)
pause
