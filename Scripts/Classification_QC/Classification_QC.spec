# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

ttkb_datas, ttkb_binaries, ttkb_hiddenimports = collect_all('ttkbootstrap')

ICO = r'C:\Users\NSENILOV\BC_LiDAR_Production\Scripts\Classification_QC\ico\QC_icon.ico'

a = Analysis(
    ['Classification_QC.py'],
    pathex=[],
    binaries=ttkb_binaries,
    datas=ttkb_datas + [(ICO, '.')],
    hiddenimports=[
        'rasterio',
        'rasterio.merge',
        'rasterio.crs',
        'rasterio.transform',
        'rasterio.sample',
        'rasterio.vrt',
        'rasterio.features',
        'rasterio.warp',
        'rasterio.mask',
        'rasterio.windows',
        'rasterio.plot',
        'rasterio._env',
        'rasterio.env',
        'colorama',
        'numpy',
        'PIL',
        'PIL.Image',
        'PIL.ImageTk',
    ] + ttkb_hiddenimports,
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
    icon=[ICO],
)
