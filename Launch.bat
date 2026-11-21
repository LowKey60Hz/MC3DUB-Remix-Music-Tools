@echo off
setlocal
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0supporting_tools\Launch_No_Shell.ps1"
if errorlevel 1 (
  echo [ERROR] Could not launch MC3 Ultimate Music Tools. See the error above.
  pause
  exit /b 1
)
endlocal
