@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Python environment not found. Run Install_MC3_GUI_Dependencies.ps1 first.
  pause
  exit /b 1
)
if not exist "gui\main.py" (
  echo [ERROR] gui\main.py not found. Place this launcher in the project root.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" "gui\main.py"
if errorlevel 1 (
  echo.
  echo [ERROR] MC3 Ultimate Music Tools exited with an error.
  pause
  exit /b 1
)
endlocal