# Build keyflip.exe.  Run from the repo root:  .\packaging\build_windows.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$py = if ($env:PYTHON) { $env:PYTHON } else { ".venv\Scripts\python.exe" }
& $py -m pip install --quiet --upgrade pyinstaller
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue

# --noconsole: no black window.  --onefile: one exe to drop in Startup.
& $py -m PyInstaller --noconfirm --clean `
    --onefile --noconsole --name keyflip `
    --paths src `
    --hidden-import keyflip.backend_win `
    --hidden-import keyflip.tray_win `
    --exclude-module tkinter --exclude-module pytest `
    packaging\launcher.py

Write-Host ""
Write-Host "Built dist\keyflip.exe"
Write-Host "  To start it at login, drop a shortcut to it in:"
Write-Host "  shell:startup   (Win+R, paste that, Enter)"
