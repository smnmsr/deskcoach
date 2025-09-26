# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

icons_datas = [
    ('src\\deskcoach\\resources\\icons\\icon.ico', 'deskcoach\\resources\\icons'),
    ('src\\deskcoach\\resources\\icons\\icon_16px.png', 'deskcoach\\resources\\icons'),
    ('src\\deskcoach\\resources\\icons\\icon_32px.png', 'deskcoach\\resources\\icons'),
    ('src\\deskcoach\\resources\\icons\\icon_180px.png', 'deskcoach\\resources\\icons'),
    ('src\\deskcoach\\resources\\icons\\icon_192px.png', 'deskcoach\\resources\\icons'),
    ('src\\deskcoach\\resources\\icons\\icon_512px.png', 'deskcoach\\resources\\icons'),
]

hidden = collect_submodules('deskcoach')

a = Analysis(
    ['src\\deskcoach\\main.py'],
    pathex=[],
    binaries=[],
    datas=icons_datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PySide6', 'shiboken6'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='DeskCoach',
    icon='src\\deskcoach\\resources\\icons\\icon.ico',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
