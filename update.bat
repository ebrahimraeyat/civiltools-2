@echo off
title civilTools - Updater
color 0E

echo ============================================================
echo            civilTools - Update ^& Run
echo ============================================================
echo.

:: Check Git
where git >nul 2>&1
if %errorlevel% neq 0 (
    echo  ERROR: Git is not installed or not in PATH.
    echo  Please run install.bat first.
    pause
    exit /b 1
)

:: Check we are inside a git repo
git rev-parse --is-inside-work-tree >nul 2>&1
if %errorlevel% neq 0 (
    echo  ERROR: This folder is not a Git repository.
    echo  Please run install.bat first or clone the repo.
    pause
    exit /b 1
)

:: Pull latest changes
echo [1/2] Pulling latest changes from GitHub ...
git pull
if %errorlevel% neq 0 (
    echo.
    echo  WARNING: git pull failed. You may have local changes.
    echo  Trying git stash then pull ...
    git stash
    git pull
    if %errorlevel% neq 0 (
        echo  ERROR: Could not update. Please resolve manually.
        pause
        exit /b 1
    )
    echo  Update succeeded. Your local changes were stashed.
    echo  Run "git stash pop" to restore them.
)
echo  Code updated.
echo.

:: Run (pixi will auto-install any new dependencies)
echo [2/2] Launching civilTools ...
echo.

where pixi >nul 2>&1
if %errorlevel% neq 0 (
    echo  pixi not found. Running full setup ...
    call "%~dp0install.bat"
    exit /b
)

pixi run start
if %errorlevel% neq 0 (
    echo.
    echo  Application exited with an error.
    pause
)
