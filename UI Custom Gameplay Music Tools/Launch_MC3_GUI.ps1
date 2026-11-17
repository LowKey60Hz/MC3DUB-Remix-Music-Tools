# Keep python.exe for child audio tools, but hide its console window.
param([switch]$ValidateOnly)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$guiPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
$guiMain = Join-Path $projectRoot 'gui\main.py'
try {
    if (-not (Test-Path -LiteralPath $guiPython -PathType Leaf)) {
        throw 'Python environment not found. Run Install_MC3_GUI_Dependencies.ps1 first.'
    }
    if (-not (Test-Path -LiteralPath $guiMain -PathType Leaf)) {
        throw 'Cannot find gui\main.py. Keep the launcher beside gui and supporting_tools.'
    }
    if ($ValidateOnly) {
        Write-Output 'GUI launcher paths verified.'
        exit 0
    }
    # These handles stay open for the GUI's lifetime. Keep them outside the
    # ISO workspace directories, which extraction may reset while we run.
    $guiLogs = Join-Path $projectRoot 'launcher_logs'
    [System.IO.Directory]::CreateDirectory($guiLogs) | Out-Null
    $launchId = [Guid]::NewGuid().ToString('N')
    Start-Process -FilePath $guiPython -ArgumentList @('gui\main.py') `
        -WorkingDirectory $projectRoot -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $guiLogs "gui_$launchId.stdout.log") `
        -RedirectStandardError (Join-Path $guiLogs "gui_$launchId.stderr.log")
} catch {
    Write-Error $_ -ErrorAction Continue
    exit 1
}
