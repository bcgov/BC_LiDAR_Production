@echo off
echo ============================================
echo  Building Classification Macro Generator
echo ============================================
echo.

:: Get the directory this .bat file lives in
set "SCRIPT_DIR=%~dp0"

:: Use the geo_env conda environment which has all the dependencies
set "GEO_ENV=%LOCALAPPDATA%\miniconda3\envs\geo_env"
set "GEO_PYTHON=%GEO_ENV%\python.exe"
set "GEO_BIN=%GEO_ENV%\Library\bin"

if not exist "%GEO_PYTHON%" (
    echo ERROR: Could not find geo_env Python at:
    echo   %GEO_PYTHON%
    echo.
    echo Make sure miniconda is installed and the geo_env environment exists.
    echo You can create it with: conda create -n geo_env python=3.9
    echo Then install deps: pip install -r requirements.txt
    pause
    exit /b 1
)

echo Using Python: %GEO_PYTHON%
echo.

:: Build the exe
:: pyproj's native extensions depend on DLLs in the conda Library\bin folder
:: that PyInstaller can't discover automatically, so we bundle them explicitly.
"%GEO_PYTHON%" -m PyInstaller --onefile --console --noupx ^
    --collect-all pyproj ^
    --collect-all laspy ^
    --add-binary "%GEO_BIN%\proj_9.dll;." ^
    --add-binary "%GEO_BIN%\sqlite3.dll;." ^
    --add-binary "%GEO_BIN%\libcurl.dll;." ^
    --add-binary "%GEO_BIN%\tiff.dll;." ^
    --add-binary "%GEO_BIN%\libssh2.dll;." ^
    --add-binary "%GEO_BIN%\libcrypto-3-x64.dll;." ^
    --add-binary "%GEO_BIN%\zlib.dll;." ^
    --add-binary "%GEO_BIN%\deflate.dll;." ^
    --add-binary "%GEO_BIN%\jpeg8.dll;." ^
    --add-binary "%GEO_BIN%\Lerc.dll;." ^
    --add-binary "%GEO_BIN%\liblzma.dll;." ^
    --add-binary "%GEO_BIN%\zstd.dll;." ^
    --icon="%SCRIPT_DIR%Macro_Generator.ico" ^
    --add-data "%SCRIPT_DIR%Macro_Generator.ico;." ^
    --add-data "%SCRIPT_DIR%urban_tiles.pkl;." ^
    --name "Classification_Macro_Generator_v4.1.2" ^
    "%SCRIPT_DIR%Classification_Macro_Generator.py"

echo.
if %ERRORLEVEL% EQU 0 (
    echo Build successful! Exe is in the "dist" folder.
) else (
    echo Build FAILED. Check the errors above.
)
echo.
pause
