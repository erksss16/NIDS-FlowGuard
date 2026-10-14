# Pretrain the SSF initial model once, then start.ps1 can load it and enter streaming immediately.
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Set-Location $PSScriptRoot

$pythonPath = Join-Path $PSScriptRoot ".venv-ssf\Scripts\python.exe"
if (-not (Test-Path $pythonPath)) {
    $pythonPath = "python"
}

$ckpt = "ckpt_nsl_percent08_epoch200_seed5011.pth"
Write-Host "Pretraining SSF checkpoint: ssf\$ckpt" -ForegroundColor Cyan

Push-Location .\ssf
& $pythonPath .\ssf.py `
    --dataset nsl `
    --epochs 200 `
    --epoch_1 2 `
    --percent 0.8 `
    --min-sample-interval 100 `
    --max-sample-interval 300 `
    --num_labeled_sample 50 `
    --opt_old_lr 100 `
    --opt_new_lr 8 `
    --new_sample_weight 3 `
    --seed 5011 `
    --seed-rounds 1 `
    --cuda 0 `
    --drift-method fdd-multidim `
    --save_ckpt $ckpt

$exitCode = $LASTEXITCODE
Pop-Location

if ($exitCode -ne 0) {
    Write-Host "Pretraining failed." -ForegroundColor Red
    exit $exitCode
}

Write-Host "Checkpoint ready: ssf\$ckpt" -ForegroundColor Green
