@echo off
echo ================================================================================
echo Building Last Return Density Checker v1.5.0
echo ================================================================================
echo.

REM Activate conda environment (adjust environment name if needed)
call conda activate geo_env
if errorlevel 1 (
    echo ERROR: Failed to activate conda environment
    pause
    exit /b 1
)

echo Conda environment activated
echo.

REM ---- Sync data assets from network NAS ----
REM Pulls Tiles_by_UTM and Water_by_UTM from the canonical V: drive location.
REM Robocopy is fast for already-synced trees and handles updates automatically.
REM Override the source by setting DATA_SOURCE before running this script.
if not defined DATA_SOURCE set "DATA_SOURCE=V:\Production_NAS\Supporting_Production_Files\Top_common\Software\GeoBC\Last_Return_Density_Checker\data"

echo Syncing data assets from:
echo   %DATA_SOURCE%

if not exist "%DATA_SOURCE%" (
    echo.
    echo ERROR: Cannot access network data source.
    echo Make sure the V: drive is mapped and you have NAS access.
    pause
    exit /b 1
)

robocopy "%DATA_SOURCE%\Tiles_by_UTM" "data\Tiles_by_UTM" /E /MT:8 /NFL /NDL /NJH /NJS
if errorlevel 8 (
    echo ERROR: Failed to sync Tiles_by_UTM from V: drive.
    pause
    exit /b 1
)

robocopy "%DATA_SOURCE%\Water_by_UTM" "data\Water_by_UTM" /E /MT:8 /NFL /NDL /NJH /NJS
if errorlevel 8 (
    echo ERROR: Failed to sync Water_by_UTM from V: drive.
    pause
    exit /b 1
)

echo Data assets synced.
echo.

REM ---- Sync PROJ and GDAL data ----
REM This script imports rasterio, finds the EXACT proj.db it uses,
REM copies it into data/proj/, then VERIFIES every BC UTM EPSG code.
REM If verification fails the build is aborted.
echo Syncing PROJ/GDAL data from rasterio...
python sync_proj_data.py
if errorlevel 1 (
    echo.
    echo ================================================================================
    echo PROJ/GDAL SYNC FAILED — BUILD ABORTED
    echo ================================================================================
    echo The bundled proj.db does not match the PROJ library in this environment.
    echo Fix your conda environment before building.
    pause
    exit /b 1
)
echo.

REM Clean previous builds
echo Cleaning previous builds...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
echo.

REM Install PyInstaller if not already installed
echo Ensuring PyInstaller is installed...
pip install pyinstaller
echo.

REM Run PyInstaller with the spec file
echo Running PyInstaller...
pyinstaller --clean --noconfirm LastReturnDensityChecker.spec
echo.

if errorlevel 1 (
    echo.
    echo ================================================================================
    echo BUILD FAILED!
    echo ================================================================================
    pause
    exit /b 1
)

echo ================================================================================
echo BUILD SUCCESSFUL!
echo ================================================================================
echo.
echo Output location: dist\LastReturnDensityChecker\
echo Main executable: dist\LastReturnDensityChecker\LastReturnDensityChecker.exe
echo.
echo You can now test the EXE by running:
echo   dist\LastReturnDensityChecker\LastReturnDensityChecker.exe
echo.
pause
