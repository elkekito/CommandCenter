@echo off
setlocal
title Build Command Center

set "PYTHON=python"
if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON=%~dp0.venv\Scripts\python.exe"

echo Installing Python dependencies...
"%PYTHON%" -m pip install -r "%~dp0requirements.lock"
if errorlevel 1 goto failed

echo Building CommandCenter.exe...
"%PYTHON%" "%~dp0build_exe.py"
if errorlevel 1 goto failed

echo.
echo Build complete: dist\CommandCenter.exe
echo User data is stored separately in the current Windows user's application data folder.
goto done

:failed
echo.
echo Build failed. Review the error output above.
exit /b 1

:done
endlocal
