param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8000
)

$pythonVersion = python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to detect Python version."
    exit 1
}

$versionParts = $pythonVersion.Trim().Split('.')
$major = [int]$versionParts[0]
$minor = [int]$versionParts[1]
if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 10)) {
    Write-Error "Python 3.10+ is required. Current version: $pythonVersion."
    exit 1
}

python -m uvicorn app.main:app --host $BindHost --port $Port --reload
