# Offline Evaluation Suite Runner (Windows / PowerShell).
# Executes functional, metric evaluation, and red-teaming test suites over captured generations.
$ErrorActionPreference = "Continue"

# Locate Python executable: prefer local virtual environment (.venv), fallback to system Python
$Py = $null
if (Test-Path ".venv\Scripts\python.exe") {
    $Py = ".venv\Scripts\python.exe"
    Write-Host "Using local virtual environment (.venv)"
} else {
    foreach ($cand in "python", "py") {
        try { & $cand --version *> $null; if ($LASTEXITCODE -eq 0) { $Py = $cand; break } } catch {}
    }
}
if (-not $Py) { 
    Write-Host "Error: Python runtime not found (python/py). Please install Python 3.10+." 
    exit 1 
}

# Ensure multi-run generation artifact exists prior to offline evaluation
if (-not (Test-Path outputs/generations.json)) {
    Write-Host "Error: Missing outputs/generations.json artifact."
    Write-Host "Run generation script first: python src/generate.py --n-runs 5"
    exit 1
}

Write-Host "==> Running Functional Tests"
& $Py -m pytest tests/test_functional.py -v

Write-Host "==> Running Offline Metric Evaluation"
& $Py -m pytest tests/test_eval.py -v

Write-Host "==> Running Red-Teaming & Security Suite"
& $Py -m pytest tests/test_redteam.py -v

Write-Host "==> Evaluation completed successfully. Quality Report: docs/results/results.md"
exit 0