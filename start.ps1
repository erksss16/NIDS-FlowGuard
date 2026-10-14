# Network traffic detection one-click startup script (PowerShell)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Host.UI.RawUI.WindowTitle = "NIDS - Running"

Set-Location $PSScriptRoot

Write-Host "=========================================" -ForegroundColor Green
Write-Host "  NIDS one-click startup" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Green
Write-Host ""

if (-not (Test-Path "logs")) {
    New-Item -ItemType Directory -Path "logs" | Out-Null
}
if (-not (Test-Path "data")) {
    New-Item -ItemType Directory -Path "data" | Out-Null
}

$processes = @()
$pythonPath = "python"
$backendOutLog = Join-Path $PSScriptRoot "logs\backend.out.log"
$backendErrLog = Join-Path $PSScriptRoot "logs\backend.err.log"
$ssfOutLog = Join-Path $PSScriptRoot "logs\ssf.out.log"
$ssfErrLog = Join-Path $PSScriptRoot "logs\ssf.err.log"
$frontendOutLog = Join-Path $PSScriptRoot "logs\frontend.out.log"
$frontendErrLog = Join-Path $PSScriptRoot "logs\frontend.err.log"

try {
    $candidatePaths = @()
    $candidatePaths += (Join-Path $PSScriptRoot ".venv-ssf\Scripts\python.exe")
    $candidatePaths += (Join-Path $PSScriptRoot "ssf\.venv-ssf\Scripts\python.exe")
    try {
        $condaBase = (& conda info --base 2>$null) -replace '\s+$', ''
    } catch {
        $condaBase = ''
    }
    if ($env:NIDS_CONDA_ENV -and $condaBase) {
        $candidatePaths += (Join-Path $condaBase "envs\$env:NIDS_CONDA_ENV\python.exe")
    }
    if ($env:CONDA_PREFIX) {
        $candidatePaths += (Join-Path $env:CONDA_PREFIX "python.exe")
    }
    if ($condaBase) {
        $candidatePaths += (Join-Path $condaBase "envs\ssf\python.exe")
        $candidatePaths += (Join-Path $condaBase "envs\Project\python.exe")
        $candidatePaths += (Join-Path $condaBase "envs\aoc_ids\python.exe")
        $candidatePaths += (Join-Path $condaBase "python.exe")
    }
    $candidatePaths += (Join-Path $env:USERPROFILE "anaconda3\envs\ssf\python.exe")
    $candidatePaths += (Join-Path $env:USERPROFILE "miniconda3\envs\ssf\python.exe")

    foreach ($candidate in $candidatePaths) {
        if ($candidate -and (Test-Path $candidate)) {
            $pythonPath = $candidate
            break
        }
    }
} catch {}

$env:NIDS_DB_BACKEND = "sqlite"
$env:NIDS_SQLITE_PATH = Join-Path $PSScriptRoot "data\ssf.sqlite3"

Write-Host "Using Python: $pythonPath" -ForegroundColor Cyan
& $pythonPath -c "import fastapi, uvicorn, numpy, pandas, sklearn, scipy, torch, pymysql" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "" -ForegroundColor Red
    Write-Host "[x] Python dependencies are missing in this environment." -ForegroundColor Red
    Write-Host "    Install them in the Python environment you use for this project:" -ForegroundColor Yellow
    Write-Host "    .\.venv-ssf\Scripts\python.exe -m pip install -r requirements.txt" -ForegroundColor White
    Write-Host "" -ForegroundColor Red
    Write-Host "    Or install them in your Anaconda environment:" -ForegroundColor Yellow
    Write-Host "    conda activate <your-env>" -ForegroundColor White
    Write-Host "    pip install -r requirements.txt" -ForegroundColor White
    Write-Host "" -ForegroundColor Red
    Write-Host "    To force this script to use a specific conda env:" -ForegroundColor Yellow
    Write-Host "    `$env:NIDS_CONDA_ENV = '<your-env>'" -ForegroundColor White
    Write-Host "    .\start.ps1" -ForegroundColor White
    exit 1
}
& $pythonPath -c "import torch, sys; raise SystemExit(0 if torch.cuda.is_available() else 1)" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "" -ForegroundColor Red
    Write-Host "[x] CUDA-enabled PyTorch is required, but this Python environment cannot use CUDA." -ForegroundColor Red
    Write-Host "    Current Python: $pythonPath" -ForegroundColor Yellow
    Write-Host "    Check it with:" -ForegroundColor Yellow
    Write-Host "    $pythonPath -c `"import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available())`"" -ForegroundColor White
    Write-Host "" -ForegroundColor Red
    Write-Host "    Install the CUDA build that matches your driver, for example:" -ForegroundColor Yellow
    Write-Host "    $pythonPath -m pip install --upgrade --force-reinstall torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu126" -ForegroundColor White
    exit 1
}
& $pythonPath -c "import sys; sys.path.insert(0, 'ssf'); import utils" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "" -ForegroundColor Red
    Write-Host "[x] SSF module dependencies are missing in this environment." -ForegroundColor Red
    Write-Host "    Please install the missing package shown by:" -ForegroundColor Yellow
    Write-Host "    $pythonPath -c `"import sys; sys.path.insert(0, 'ssf'); import utils`"" -ForegroundColor White
    exit 1
}
Write-Host ""

Write-Host "[1/4] Initializing SQLite database..." -ForegroundColor Yellow
if (Test-Path "data\ssf.sqlite3") {
    Remove-Item "data\ssf.sqlite3" -Force
    Write-Host "      [ok] Removed old SQLite file" -ForegroundColor Green
}
Write-Host "      [ok] SQLite database path: $env:NIDS_SQLITE_PATH" -ForegroundColor Green

Write-Host ""

Write-Host "[2/4] Starting backend API (FastAPI)..." -ForegroundColor Yellow
$port8000 = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if (-not $port8000) {
    $backendProcess = Start-Process -FilePath $pythonPath `
        -ArgumentList @("backend.py") `
        -RedirectStandardOutput $backendOutLog `
        -RedirectStandardError $backendErrLog `
        -PassThru -WindowStyle Hidden
    $processes += $backendProcess
    Start-Sleep -Seconds 2
    Write-Host "      [ok] Backend started (PID: $($backendProcess.Id), port: 8000)" -ForegroundColor Green
} else {
    Write-Host "      [!] Port 8000 is already in use; reusing the existing backend." -ForegroundColor Yellow
}
Write-Host ""

Write-Host "[3/4] Starting SSF model..." -ForegroundColor Yellow
$ssfCheckpoint = "ckpt_nsl_percent08_epoch200_seed5011.pth"
if (-not (Test-Path (Join-Path $PSScriptRoot "ssf\$ssfCheckpoint"))) {
    Write-Host "      [x] Missing pretrained checkpoint: ssf\$ssfCheckpoint" -ForegroundColor Red
    Write-Host "          Run .\pretrain-ssf.ps1 once, then start the project again." -ForegroundColor Yellow
    exit 1
}
$ssfArgs = @(
    "ssf.py",
    "--dataset", "nsl",
    "--epochs", "200",
    "--epoch_1", "2",
    "--percent", "0.8",
    "--min-sample-interval", "100",
    "--max-sample-interval", "300",
    "--num_labeled_sample", "50",
    "--opt_old_lr", "100",
    "--opt_new_lr", "8",
    "--new_sample_weight", "3",
    "--seed", "5011",
    "--seed-rounds", "5",
    "--cuda", "0",
    "--load_ckpt", $ssfCheckpoint,
    "--skip_initial_eval",
    "--stream",
    "--stream-delay", "1",
    "--drift-method", "fdd-multidim",
    "--mysql",
    "--db-backend", "sqlite",
    "--sqlite-path", "..\data\ssf.sqlite3"
)
$ssfProcess = Start-Process -FilePath $pythonPath `
    -ArgumentList $ssfArgs `
    -WorkingDirectory "ssf" `
    -RedirectStandardOutput $ssfOutLog `
    -RedirectStandardError $ssfErrLog `
    -PassThru -WindowStyle Hidden
$processes += $ssfProcess
Start-Sleep -Seconds 2
if ($ssfProcess.HasExited) {
    Write-Host "      [x] SSF model exited immediately. See logs\ssf.err.log for details." -ForegroundColor Red
    exit 1
}
Write-Host "      [ok] SSF model started (PID: $($ssfProcess.Id))" -ForegroundColor Green
Write-Host ""

Write-Host "[4/4] Starting frontend (Vue + Vite)..." -ForegroundColor Yellow
$port5173 = Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue
if (-not $port5173) {
    $frontendProcess = Start-Process -FilePath "cmd" `
        -ArgumentList @("/c", "npm run dev") `
        -RedirectStandardOutput $frontendOutLog `
        -RedirectStandardError $frontendErrLog `
        -PassThru -WindowStyle Hidden
    $processes += $frontendProcess
    Start-Sleep -Seconds 3
    Write-Host "      [ok] Frontend started (PID: $($frontendProcess.Id), port: 5173)" -ForegroundColor Green
} else {
    Write-Host "      [!] Port 5173 is already in use; reusing the existing frontend." -ForegroundColor Yellow
}
Write-Host ""

Write-Host "=========================================" -ForegroundColor Green
Write-Host "  All services are running" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Frontend: http://localhost:5173" -ForegroundColor White
Write-Host "  Backend API: http://localhost:8000" -ForegroundColor White
Write-Host "  API docs: http://localhost:8000/docs" -ForegroundColor White
Write-Host "  Database: SQLite @ $env:NIDS_SQLITE_PATH" -ForegroundColor White
Write-Host ""
Write-Host "  Press Ctrl+C to stop all services..." -ForegroundColor Yellow
Write-Host ""

try {
    while ($true) {
        Start-Sleep -Seconds 1
    }
} finally {
    Write-Host ""
    Write-Host "=========================================" -ForegroundColor Yellow
    Write-Host "  Stopping services..." -ForegroundColor Yellow
    Write-Host "=========================================" -ForegroundColor Yellow
    Write-Host ""

    function Kill-ByPort($port) {
        netstat -ano 2>$null | Select-String ":$port" | Select-String "LISTENING" | ForEach-Object {
            $parts = $_ -replace '^\s+', '' -split '\s+'
            $id = $parts[-1]
            if ($id -match '^\d+$') { & taskkill /T /F /PID $id 2>$null | Out-Null }
        }
    }

    Write-Host "[1/3] Stopping frontend..." -ForegroundColor Yellow
    if ($frontendProcess -and -not $frontendProcess.HasExited) {
        & taskkill /T /F /PID $frontendProcess.Id 2>$null | Out-Null
    }
    Kill-ByPort 5173
    Write-Host "      [ok] Frontend stopped" -ForegroundColor Green

    Write-Host "[2/3] Stopping backend API..." -ForegroundColor Yellow
    if ($backendProcess -and -not $backendProcess.HasExited) {
        & taskkill /T /F /PID $backendProcess.Id 2>$null | Out-Null
    }
    Kill-ByPort 8000
    Write-Host "      [ok] Backend stopped" -ForegroundColor Green

    Write-Host "[3/3] Stopping SSF model..." -ForegroundColor Yellow
    if ($ssfProcess -and -not $ssfProcess.HasExited) {
        & taskkill /T /F /PID $ssfProcess.Id 2>$null | Out-Null
    }
    Write-Host "      [ok] SSF model stopped" -ForegroundColor Green

    Write-Host ""
    Write-Host "=========================================" -ForegroundColor Green
    Write-Host "  All services stopped" -ForegroundColor Green
    Write-Host "=========================================" -ForegroundColor Green
    Start-Sleep -Seconds 2
}
