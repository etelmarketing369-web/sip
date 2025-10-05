@echo off
echo Installing Windows SIP Dialer Dependencies...
echo.

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8+ from https://www.python.org/
    pause
    exit /b 1
)

echo Python is installed, proceeding with package installation...
echo.

REM Install pjsua2 (PJSIP Python bindings)
echo Installing PJSIP Python bindings...
pip install sounddevice vosk requests numpy pyautogui datetime  pyadio
pip install pjsua2

if %errorlevel% neq 0 (
    echo.
    echo WARNING: Failed to install pjsua2 using pip.
    echo You may need to install PJSIP manually or use a wheel file.
    echo.
    echo Alternative installation methods:
    echo 1. Download precompiled PJSIP from: https://www.pjsip.org/download.htm
    echo 2. Use conda: conda install -c conda-forge pjsip
    echo 3. Build from source following PJSIP documentation
    echo.
)

REM tkinter is included with Python, so no need to install it separately

echo.
echo Installation completed!
echo.
echo To run the SIP Dialer:
echo   python main.py
echo.
pause
