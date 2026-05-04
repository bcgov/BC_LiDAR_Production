@echo off
echo ============================================
echo  Building Classification Macro Generator
echo ============================================
echo.
:: Get the directory this .bat file lives in
set "SCRIPT_DIR=%~dp0"
:: Use the lidar conda environment which has all the dependencies
set "LIDAR_ENV=C:\Users\SFLOYD\AppData\Local\miniconda3\envs\lidar"
set "LIDAR_PYTHON=%LIDAR_ENV%\python.exe"
set "LIDAR_BIN=%LIDAR_ENV%\Library\bin"
if not exist "%LIDAR_PYTHON%" (
    echo ERROR: Could not find lidar Python at:
    echo   %LIDAR_PYTHON%
    echo.
    echo Make sure miniconda is installed and the lidar environment exists.
    echo You can create it with: conda create -n lidar python=3.9
    echo Then install deps: pip install -r requirements.txt
    pause
    exit /b 1
)
echo Using Python: %LIDAR_PYTHON%
echo.
:: Build the exe
:: pyproj's native extensions depend on DLLs in the conda Library\bin folder
:: that PyInstaller can't discover automatically, so we bundle them explicitly.
"%LIDAR_PYTHON%" -m PyInstaller --onefile --console --noupx ^
    --collect-all pyproj ^
    --collect-all laspy ^
    --add-binary "%LIDAR_BIN%\proj_9_4.dll;." ^
    --add-binary "%LIDAR_BIN%\sqlite3.dll;." ^
    --add-binary "%LIDAR_BIN%\libcurl.dll;." ^
    --add-binary "%LIDAR_BIN%\tiff.dll;." ^
    --add-binary "%LIDAR_BIN%\libssh2.dll;." ^
    --add-binary "%LIDAR_BIN%\libcrypto-3-x64.dll;." ^
    --add-binary "%LIDAR_BIN%\zlib.dll;." ^
    --add-binary "%LIDAR_BIN%\deflate.dll;." ^
    --add-binary "%LIDAR_BIN%\jpeg8.dll;." ^
    --add-binary "%LIDAR_BIN%\Lerc.dll;." ^
    --add-binary "%LIDAR_BIN%\liblzma.dll;." ^
    --add-binary "%LIDAR_BIN%\zstd.dll;." ^
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