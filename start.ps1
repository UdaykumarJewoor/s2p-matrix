# start.ps1 — Launch S2P Backend on Windows
# Sets UTF-8 mode so emoji in source files don't cause import errors
# Usage: .\start.ps1

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

Write-Host ""
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "  Matrix S2P Automation System v2.1" -ForegroundColor Cyan
Write-Host "  Starting FastAPI backend on http://localhost:8000" -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host ""

Set-Location "$PSScriptRoot\backend"
& "$PSScriptRoot\venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
