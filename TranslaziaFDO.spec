# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules


hiddenimports = []
hiddenimports += collect_submodules('vk_video_analyzer')
hiddenimports += collect_submodules('soundchecker')
hiddenimports += [
    'cv2',
    'imageio_ffmpeg',
    'matplotlib.backends.backend_agg',
    'ultralytics',
]


a = Analysis(
    ['run_client.py'],
    pathex=[
        'vendor\\Module_video_analys',
        'vendor\\SoundChecker',
    ],
    binaries=[],
    datas=[
        ('translazia_client\\assets', 'translazia_client\\assets'),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TranslaziaFDO',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['translazia_client\\assets\\logo_fdo.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='TranslaziaFDO',
)
