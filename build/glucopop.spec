# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — run from repo root:  pyinstaller build/glucopop.spec
import os
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None
root = os.path.abspath(os.path.join(SPECPATH, ".."))

a = Analysis(
    [os.path.join(root, "run.py")],
    pathex=[root],
    binaries=[],
    datas=[],
    hiddenimports=collect_submodules("keyring.backends") + ["winsound", "truststore"],
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
exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
    name="GlucoPop",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,               # no console window
    icon=os.path.join(root, "assets", "glucopop.ico"),
    version=os.path.join(root, "build", "version_info.txt"),
)
