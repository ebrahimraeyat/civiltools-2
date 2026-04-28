@echo off
title civilTools
color 0A

echo ============================================================
echo              civilTools - Launcher
echo ============================================================
echo.

:: Check pixi is available
where pixi >nul 2>&1
if %errorlevel% neq 0 (
    echo  pixi not found. Running full setup ...
    echo.
    call "%~dp0install.bat"
    exit /b
)

:: Check that pixi environment exists
if not exist ".pixi" (
    echo  Environment not found. Running full setup ...
    echo.
    call "%~dp0install.bat"
    exit /b
)

echo  Starting civilTools ...
echo.
pixi run start
if %errorlevel% neq 0 (
    echo.
    echo  Application exited with an error.
    pause
)
