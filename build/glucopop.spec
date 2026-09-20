# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — run from repo root:  pyinstaller build/glucopop.spec
import os
import sys
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None
root = os.path.abspath(os.path.join(SPECPATH, ".."))

a = Analysis(
    [os.path.join(root, "run.py")],
    pathex=[root],
    binaries=[],
    datas=[],
    hiddenimports=collect_submodules("keyring.backends") + ["truststore"]
                  + (["winsound"] if sys.platform == "win32" else []),
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # trim Qt modules we do not use
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml", "PySide6.QtQuick",
        "PySide6.QtQuick3D", "PySide6.QtMultimedia", "PySide6.QtPdf", "PySide6.QtCharts", "PySide6.Qt3DCore",
        "PySide6.QtDataVisualization", "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtSql", "PySide6.QtTest",
        "PySide6.QtLocation", "PySide6.QtPositioning", "PySide6.QtRemoteObjects", "PySide6.QtSensors",
        "PySide6.QtSerialPort", "PySide6.QtWebSockets", "PySide6.QtWebChannel", "PySide6.QtDesigner",
        "PySide6.QtHelp", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtSvgWidgets", "PySide6.QtXml",
        "PySide6.QtNetworkAuth", "PySide6.QtStateMachine", "PySide6.QtScxml", "PySide6.QtTextToSpeech",
        "PySide6.QtHttpServer", "PySide6.QtSpatialAudio", "PySide6.QtGraphs", "tkinter",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
MAC = sys.platform == "darwin"

# read from the one place the version lives, rather than repeating it here where it would drift
import re as _re
VERSION = _re.search(r'VERSION\s*=\s*"([^"]+)"',
                     open(os.path.join(root, "glucopop", "config.py"), encoding="utf-8").read()).group(1)

exe = EXE(
    pyz, a.scripts,
    *([] if MAC else [a.binaries, a.zipfiles, a.datas]), [],
    name="GlucoPop",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,               # no console window
    # a .app carries its own icon; the executable inside it does not need one
    icon=None if MAC else os.path.join(root, "assets", "glucopop.ico"),
    version=None if MAC else os.path.join(root, "build", "version_info.txt"),
    # codesign runs as its own step in the workflow, over the finished bundle
    codesign_identity=None,
    entitlements_file=None,
    exclude_binaries=MAC,
)

# macOS wants a folder, not one file: a single-file bundle unpacks itself to a temporary
# directory on every launch, which breaks the code signature Gatekeeper verified and makes a
# menu-bar app take seconds to appear. Windows keeps the one-file build.
if MAC:
    coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, strip=False, upx=False, name="GlucoPop")
    app = BUNDLE(
        coll,
        name="GlucoPop.app",
        icon=os.path.join(root, "assets", "glucopop.icns"),
        bundle_identifier="com.typehealthy.glucopop",
        version=VERSION,
        info_plist={
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "LSMinimumSystemVersion": "11.0",
            "NSHighResolutionCapable": True,
            # lives in the menu bar: no Dock icon, no Cmd-Tab entry, like every other
            # always-there status app
            "LSUIElement": True,
            "NSHumanReadableCopyright": "© 2026 Emre Kılıç · MIT",
        },
    )
