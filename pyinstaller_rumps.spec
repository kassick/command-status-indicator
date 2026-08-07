# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for building the Command Status Indicator macOS app using rumps.
"""

import os
from pathlib import Path

cipher = None

a = Analysis(
    ['command_status_indicator/main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('command_status_indicator/icons', 'command_status_indicator/icons'),
    ],
    hiddenimports=[
        'rumps',
        'PIL',
        'PIL.Image',
        'PIL.ImageDraw',
        # New modules from the refactor — PyInstaller often auto-detects relative
        # imports but listing them explicitly ensures they're bundled.
        'command_status_indicator.config',
        'command_status_indicator.frontend_osx',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludedimports=[
        # Linux-only modules — must not be pulled in on macOS
        'command_status_indicator.frontend_linux',
        'gi',
        'gi.repository',
        'gi.repository.Gtk',
        'gi.repository.AppIndicator3',
        'gi.repository.GLib',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='command-status-indicator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='command_status_indicator/icons/app-icon.png' if os.path.exists('command_status_indicator/icons/app-icon.png') else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='command-status-indicator',
)

app = BUNDLE(
    coll,
    name='Command Status Indicator.app',
    icon='command_status_indicator/icons/app-icon.png' if os.path.exists('command_status_indicator/icons/app-icon.png') else None,
    bundle_identifier='com.kzk.command-status-indicator',
    info_plist={
        'NSPrincipalClass': 'NSApplication',
        'NSHighResolutionCapable': 'True',
        'LSUIElement': True,
    },
)
