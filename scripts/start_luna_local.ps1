param([string]$PythonPath = "")
$ErrorActionPreference = 'Stop'
$taskRepo = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $taskRepo
if (-not $PythonPath) { $PythonPath = Join-Path $taskRepo '.venv\Scripts\python.exe' }
if (-not (Test-Path -LiteralPath $PythonPath)) { throw 'Create .venv and install requirements-dev.txt first. See docs/OCR_PROTOTYPE.md.' }
$taskPython = (Resolve-Path -LiteralPath $PythonPath).Path
if (-not (Test-Path -LiteralPath (Join-Path $taskRepo '.env'))) { throw 'Copy .env.example to .env and configure DB and keys first.' }
foreach ($taskPort in @(18785,18786)) {
    if (Get-NetTCPConnection -LocalPort $taskPort -State Listen -ErrorAction SilentlyContinue) { throw "Port $taskPort already in use; stop the earlier local run explicitly." }
}
# Read-only preflight: never reset, stamp, migrate or overwrite environment files.
& $taskPython -c "from sqlalchemy import inspect; from app.core.database import engine, SQLModel; missing=set(SQLModel.metadata.tables)-set(inspect(engine).get_table_names()); assert not missing, 'Apply reviewed Alembic migrations first: '+str(sorted(missing))"
if ($LASTEXITCODE -ne 0) { throw 'Database preflight failed; no service processes started.' }
$taskVite = Join-Path $taskRepo 'frontend\node_modules\vite\bin\vite.js'
if (-not (Test-Path -LiteralPath $taskVite)) { throw 'Run npm ci in frontend first.' }
$taskApi = Start-Process -FilePath $taskPython -ArgumentList @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port','18785') -WorkingDirectory $taskRepo -WindowStyle Hidden -PassThru
$taskWorker = Start-Process -FilePath $taskPython -ArgumentList @('-m','app.jobs.worker') -WorkingDirectory $taskRepo -WindowStyle Hidden -PassThru
$env:VITE_API_URL = 'http://127.0.0.1:18785'
$taskFrontend = Start-Process -FilePath (Get-Command node).Source -ArgumentList @(('"'+$taskVite+'"'),'--host','127.0.0.1','--port','18786','--strictPort') -WorkingDirectory (Join-Path $taskRepo 'frontend') -WindowStyle Hidden -PassThru
@{api=$taskApi.Id;worker=$taskWorker.Id;frontend=$taskFrontend.Id;url='http://127.0.0.1:18786'} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskRepo 'storage\local_processes.json') -Encoding utf8
Write-Output 'Local service: http://127.0.0.1:18786 ; API: http://127.0.0.1:18785/docs'
