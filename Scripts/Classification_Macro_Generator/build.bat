@echo off
echo ============================================
echo  Building Classification Macro Generator
echo ============================================
echo.

:: Get the directory this .bat file lives in
set "SCRIPT_DIR=%~dp0"

:: Build the exe
pyinstaller --onefile --console --noupx ^
    --collect-all pyproj ^
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
