# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Aura — produces a single portable .exe
# Build command (run from project root):  uv run pyinstaller aura.spec

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

# Collect PySide6 Qt plugins and binaries needed for the app
pyside6_datas = collect_data_files("PySide6", includes=["*.dll", "plugins/**/*"])
soundfile_datas = collect_data_files("soundfile")

a = Analysis(
    ["src/aura/main.py"],
    pathex=["."],
    binaries=collect_dynamic_libs("sounddevice"),
    datas=[
        *pyside6_datas,
        *soundfile_datas,
    ],
    hiddenimports=[
        # pynput Windows backend
        "pynput.keyboard._win32",
        "pynput.mouse._win32",
        # sounddevice / soundfile
        "sounddevice",
        "soundfile",
        "_sounddevice",
        # openai internal transport
        "httpx",
        "httpcore",
        "anyio",
        "certifi",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "scipy",
        "PIL",
        "pytest",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="Aura",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=["vcruntime140.dll", "ucrtbase.dll"],
    runtime_tmpdir=None,
    console=False,          # no console window — background tray app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,              # TODO: replace with "assets/tray_icon.ico" once the asset is created
)
