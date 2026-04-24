# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

# Get the directory containing this spec file
spec_root = Path(SPECPATH)

block_cipher = None

a = Analysis(
    ['Last_Return_Density_Analysis.py'],
    pathex=[],
    binaries=[],
    datas=[
        # Include data folders
        ('data/gdal', 'data/gdal'),
        ('data/proj', 'data/proj'),
        ('data/Tiles_by_UTM', 'data/Tiles_by_UTM'),
        ('data/Water_by_UTM', 'data/Water_by_UTM'),
        # Include icon asset
        ('assets/LastReturnDensityChecker_Icon.ico', 'assets'),
    ],
    hiddenimports=[
        'numpy',
        'fiona',
        'fiona._shim',
        'fiona.schema',
        'rasterio',
        'rasterio._shim',
        'rasterio.control',
        'rasterio.crs',
        'rasterio.sample',
        'rasterio.vrt',
        'rasterio._features',
        'shapely.geometry',
        'pyproj',
        'certifi',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'PIL',
        'IPython',
        'jupyter',
        'notebook',
        'pandas',
        'scipy',
        'torch',
        'tensorflow',
    ],
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
    name='LastReturnDensityChecker',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # Set to False for GUI app (no console window)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/LastReturnDensityChecker_Icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='LastReturnDensityChecker',
)
