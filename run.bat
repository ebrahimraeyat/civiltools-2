@echo off
title civilTools
color 0A

echo ============================================================
echo              civilTools - Launcher
echo ============================================================
echo.

:: Check conda is available
where conda >nul 2>&1
if %errorlevel% neq 0 (
    echo  conda not found. Running full setup ...
    echo.
    call "%~dp0install.bat"
    exit /b
)

:: Check that the civiltools conda environment exists
call conda env list | findstr /C:"civiltools" >nul 2>&1
if %errorlevel% neq 0 (
    echo  Environment not found. Running full setup ...
    echo.
    call "%~dp0install.bat"
    exit /b
)

echo  Compiling Qt resources ...
call conda run -n civiltools pyside6-rcc "%~dp0src\civiltools\gui\civiltools.qrc" -o "%~dp0src\civiltools\gui\civiltools_rc.py"
if %errorlevel% neq 0 (
    echo.
    echo  Failed to compile Qt resources.
    pause
    exit /b 1
)

echo  Starting civilTools ...
echo.
call conda run -n civiltools python -m civiltools
if %errorlevel% neq 0 (
    echo.
    echo  Application exited with an error.
    pause
)
