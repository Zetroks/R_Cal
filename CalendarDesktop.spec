# -*- mode: python ; coding: utf-8 -*-
# PyInstaller one-dir spec для десктоп-клиента.
# Версия вшита из CalendarService/version.py (тот же репозиторий).
# Сборка:  bump_version.py -> commit -> tag v... -> pyinstaller CalendarDesktop.spec
# Релиз собирается в CI (.github/workflows/build.yml).

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

a = Analysis(
    ['run_desktop.py'],
    pathex=[],
    binaries=[],
    datas=[('CalendarDesktop/data', 'CalendarDesktop/data')],
    hiddenimports=collect_submodules('CalendarDesktop.MultiFields'),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='R_Cal',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='R_Cal',
)
