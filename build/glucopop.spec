# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — run from repo root:  pyinstaller build/glucopop.spec
# Produces a folder, dist/GlucoPop/ (GlucoPop.exe and its _internal/ files), and on macOS GlucoPop.app.
import os
import re
import sys
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None
root = os.path.abspath(os.path.join(SPECPATH, ".."))
MAC = sys.platform == "darwin"
WIN = sys.platform == "win32"

a = Analysis(
    [os.path.join(root, "run.py")],
    pathex=[root],
    binaries=[],
    datas=[],
    # Qt WebEngine (the Medtronic sign-in window) is imported only when that window opens, so the
    # import analysis would not see it on its own.
    hiddenimports=collect_submodules("keyring.backends") + ["truststore", "PySide6.QtWebEngineCore",
                                                            "PySide6.QtWebEngineWidgets"]
                  + (["winsound"] if WIN else []),
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # trim Qt modules we do not use. Not in this list, because the Medtronic sign-in window
        # needs them: QtWebEngineCore, QtWebEngineWidgets, QtWebChannel (and QtNetwork,
        # QtPrintSupport, which were never here). Qt WebEngine's own libraries still bring the Qt
        # Quick/QML/Positioning *libraries* along; only their Python modules are left out.
        "PySide6.QtQml", "PySide6.QtQuick",
        "PySide6.QtQuick3D", "PySide6.QtMultimedia", "PySide6.QtPdf", "PySide6.QtCharts", "PySide6.Qt3DCore",
        "PySide6.QtDataVisualization", "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtSql", "PySide6.QtTest",
        "PySide6.QtLocation", "PySide6.QtPositioning", "PySide6.QtRemoteObjects", "PySide6.QtSensors",
        "PySide6.QtSerialPort", "PySide6.QtWebSockets", "PySide6.QtDesigner",
        "PySide6.QtHelp", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtSvgWidgets", "PySide6.QtXml",
        "PySide6.QtNetworkAuth", "PySide6.QtStateMachine", "PySide6.QtScxml", "PySide6.QtTextToSpeech",
        "PySide6.QtHttpServer", "PySide6.QtSpatialAudio", "PySide6.QtGraphs", "tkinter",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Qt WebEngine carries its own interface strings (a page's right-click menu, form hints) in some
# fifty languages. GlucoPop speaks Turkish and English, and English is Chromium's fallback for the
# rest, so the other packs are ~30 MB nobody would see.
KEEP_LOCALES = {"en-US.pak", "en-GB.pak", "tr.pak"}
a.datas = [d for d in a.datas
           if "qtwebengine_locales" not in d[0].replace("\\", "/") or os.path.basename(d[0]) in KEEP_LOCALES]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# read from the one place the version lives, rather than repeating it here where it would drift
VERSION = re.search(r'VERSION\s*=\s*"([^"]+)"',
                    open(os.path.join(root, "glucopop", "config.py"), encoding="utf-8").read()).group(1)

# Windows version resource: the template in build/version_info.txt, with the version filled in
version_file = None
if WIN:
    parts = [int(x) for x in re.findall(r"\d+", VERSION)[:4]]
    template = open(os.path.join(root, "build", "version_info.txt"), encoding="utf-8").read()
    os.makedirs(workpath, exist_ok=True)
    version_file = os.path.join(workpath, "version_info.txt")
    with open(version_file, "w", encoding="utf-8") as f:
        f.write(template.replace("@VERSION_TUPLE@", repr(tuple((parts + [0, 0, 0, 0])[:4])))
                        .replace("@VERSION@", VERSION))

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="GlucoPop",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,               # no console window
    # a .app carries its own icon; the executable inside it does not need one
    icon=os.path.join(root, "assets", "glucopop.ico") if WIN else None,
    version=version_file,
    # codesign runs as its own step in the workflow, over the finished bundle
    codesign_identity=None,
    entitlements_file=None,
)

# A folder, not one file, on both systems. A single-file build unpacks itself to a temporary
# directory on every launch — with Qt WebEngine inside, a few hundred megabytes, every time the
# computer starts — and on macOS it also breaks the code signature Gatekeeper verified.
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, strip=False, upx=False, name="GlucoPop")

if MAC:
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
