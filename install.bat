@echo off
title civilTools - Installer
color 0A

echo ============================================================
echo           civilTools - One-Click Installer
echo ============================================================
echo.

:: ---------------------------------------------------------------
:: 1. Check / install Git
:: ---------------------------------------------------------------
echo [1/3] Checking Git ...
where git >nul 2>&1
if %errorlevel% equ 0 goto :git_ok

echo      Git not found. Downloading Git installer ...
echo      Git will be installed silently (this may take a minute).
echo.
set "GIT_INSTALLER=%TEMP%\git-installer.exe"
set "PS_PATH=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
"%PS_PATH%" -NoProfile -Command "& { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://github.com/git-for-windows/git/releases/latest/download/Git-2.47.1-64-bit.exe' -OutFile '%TEMP%\git-installer.exe' }"
if not exist "%GIT_INSTALLER%" (
    echo      ERROR: Failed to download Git installer.
    echo      Please install Git manually from https://git-scm.com/downloads
    pause
    exit /b 1
)
start /wait "" "%GIT_INSTALLER%" /VERYSILENT /NORESTART /NOCANCEL /SP- /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS /COMPONENTS="icons,ext\reg\shellhere,assoc,assoc_sh"
del "%GIT_INSTALLER%" 2>nul

call :refresh_path
where git >nul 2>&1
if %errorlevel% neq 0 (
    echo      Git installation may require reopening this terminal.
    echo      Please close this window and double-click install.bat again.
    pause
    exit /b 1
)
echo      Git installed successfully.
goto :git_done

:git_ok
echo      Git found.

:git_done
echo.

:: ---------------------------------------------------------------
:: 2. Check / install conda (Miniconda)
:: ---------------------------------------------------------------
echo [2/3] Checking conda ...
where conda >nul 2>&1
if %errorlevel% equ 0 goto :conda_ok

echo      conda not found. Installing Miniconda ...
set "CONDA_INSTALLER=%TEMP%\miniconda-installer.exe"
set "PS_PATH=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
"%PS_PATH%" -NoProfile -Command "& { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe' -OutFile '%CONDA_INSTALLER%' }"
if not exist "%CONDA_INSTALLER%" (
    echo      ERROR: Failed to download Miniconda installer.
    echo      Please install Miniconda manually from https://docs.conda.io/en/latest/miniconda.html
    pause
    exit /b 1
)
start /wait "" "%CONDA_INSTALLER%" /InstallationType=JustMe /RegisterPython=0 /AddToPath=1 /S /D=%UserProfile%\Miniconda3
del "%CONDA_INSTALLER%" 2>nul

call :refresh_path
where conda >nul 2>&1
if %errorlevel% neq 0 (
    echo      conda installation may require reopening this terminal.
    echo      Please close this window and double-click install.bat again.
    pause
    exit /b 1
)
echo      Miniconda installed successfully.
goto :conda_done

:conda_ok
echo      conda found.

:conda_done
echo.

:: ---------------------------------------------------------------
:: 3. Create environment and run
:: ---------------------------------------------------------------
echo [3/3] Setting up environment and launching civilTools ...
echo      (First run downloads Python, pythonocc-core, and all
echo       dependencies. This may take several minutes.)
echo.

call conda env list | findstr /C:"civiltools" >nul 2>&1
if %errorlevel% equ 0 goto :env_exists

echo      Creating conda environment "civiltools" ...
call conda create -y -n civiltools python=3.12 pythonocc-core=7.9 -c conda-forge
if %errorlevel% neq 0 (
    echo.
    echo      ERROR: Failed to create the conda environment.
    pause
    exit /b 1
)

:env_exists
echo      Installing civilTools and its dependencies ...
call conda run -n civiltools pip install -e "%~dp0.[dev]"
if %errorlevel% neq 0 (
    echo.
    echo      ERROR: Failed to install dependencies.
    pause
    exit /b 1
)

call conda run -n civiltools python -m civiltools
if %errorlevel% neq 0 (
    echo.
    echo      ERROR: Application failed to start.
    echo      Check the error messages above.
    pause
    exit /b 1
)

pause
goto :eof

:: ---------------------------------------------------------------
:: Subroutine: Refresh PATH from registry
:: ---------------------------------------------------------------
:refresh_path
for /f "tokens=2,*" %%A in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "SYS_PATH=%%B"
for /f "tokens=2,*" %%A in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USR_PATH=%%B"
set "PATH=%SYS_PATH%;%USR_PATH%"
goto :eof
