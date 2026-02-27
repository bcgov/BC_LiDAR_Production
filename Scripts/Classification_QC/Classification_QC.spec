# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['Classification_QC.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'rasterio',
        'rasterio.merge',
        'rasterio.crs',
        'rasterio._env',
        'rasterio.env',
        'colorama',
        'numpy',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['shapely'],
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
    name='Classification_QC',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[r'Z:\SPENCER_FLOYD\.ico\Classification_QC.ico'],
)
