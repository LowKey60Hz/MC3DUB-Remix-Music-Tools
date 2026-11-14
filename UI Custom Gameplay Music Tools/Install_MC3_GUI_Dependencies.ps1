# MC3 Ultimate Music Tools - Windows setup (PowerShell 5.1+)
# Run from any location; the project root is the folder containing this script.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $root
$venvPython = Join-Path $root '.venv\Scripts\python.exe'
$launcher = Join-Path $root 'Launch_MC3_GUI.bat'

function Fail([string]$message) { throw $message }
function Run-Checked([string]$exe, [string[]]$arguments) {
    & $exe @arguments
    if ($LASTEXITCODE -ne 0) { Fail "Command failed (exit $LASTEXITCODE): $exe $($arguments -join ' ')" }
}
function Find-Python312 {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        & $py.Source -3.12 -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3,12) else 1)' 2>$null
        if ($LASTEXITCODE -eq 0) { return @{ exe=$py.Source; args=@('-3.12') } }
    }
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
        (Join-Path $env:ProgramFiles 'Python312\python.exe')
    )
    foreach ($p in $candidates) {
        if (Test-Path -LiteralPath $p) { return @{ exe=$p; args=@() } }
    }
    return $null
}

Write-Host '=== MC3 Ultimate Music Tools - Windows Setup ===' -ForegroundColor Cyan
if (-not (Test-Path -LiteralPath (Join-Path $root 'gui\main.py'))) {
    Fail 'Cannot find gui\main.py. Put this installer in the project root (next to gui and supporting_tools).'
}

$python = Find-Python312
if (-not $python) {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) { Fail 'Python 3.12 not found and winget is unavailable. Install Python 3.12 from python.org, then rerun.' }
    Write-Host 'Installing Python 3.12 with winget...'
    Run-Checked $winget.Source @('install','--id','Python.Python.3.12','--exact','--source','winget','--accept-package-agreements','--accept-source-agreements')
    $python = Find-Python312
    if (-not $python) { Fail 'Python installed but was not detected. Close and reopen PowerShell, then rerun setup.' }
}
Write-Host 'Python 3.12 found.' -ForegroundColor Green

if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host 'Creating .venv...'
    Run-Checked $python.exe ($python.args + @('-m','venv',(Join-Path $root '.venv')))
} else {
    Write-Host 'Reusing existing .venv.'
}

Write-Host 'Installing/updating Python dependencies...'
Run-Checked $venvPython @('-m','pip','install','--upgrade','pip')
Run-Checked $venvPython @('-m','pip','install','PySide6>=6.7,<7','numpy>=1.26,<3','scipy>=1.12,<2','soundfile>=0.12,<1','sounddevice>=0.4.6,<1')
Run-Checked $venvPython @('-m','pip','check')

# Pipe Python source to stdin to avoid Windows PowerShell native-argument quote stripping.
$checkCode = @'
import PySide6
import numpy
import scipy
import soundfile
import sounddevice
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
print('All dependencies OK')
'@
$checkCode | & $venvPython -
if ($LASTEXITCODE -ne 0) { Fail 'Python import verification failed.' }

Write-Host 'Checking bundled supporting tools...'
$required = @('supporting_tools\ps2str.exe','supporting_tools\encvag.dll','supporting_tools\MFAudio.exe')
$missing = @()
foreach ($relative in $required) {
    if (Test-Path -LiteralPath (Join-Path $root $relative)) { Write-Host "  OK: $relative" }
    else { $missing += $relative; Write-Warning "Missing: $relative" }
}

# Launcher uses its own location, so it works even when the folder is moved.
$bat = @'
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
'@
[System.IO.File]::WriteAllText($launcher, ($bat -replace "`n", "`r`n"), [System.Text.Encoding]::ASCII)
Write-Host "Launcher created: $launcher" -ForegroundColor Green
if ($missing.Count -gt 0) {
    Write-Warning 'Setup completed, but some bundled supporting files are missing. Copy them from the complete project distribution before using audio conversion.'
} else {
    Write-Host 'Setup complete. Double-click Launch_MC3_GUI.bat to start the GUI.' -ForegroundColor Green
}
