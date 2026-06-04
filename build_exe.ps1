$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root "venv\Scripts\python.exe"
$PyInstaller = Join-Path $Root "venv\Scripts\pyinstaller.exe"
$DistApp = Join-Path $Root "dist\TranslaziaFDO"

if (-not (Test-Path $Python)) {
    throw "Python not found: $Python"
}

if (-not (Test-Path $PyInstaller)) {
    & $Python -m pip install pyinstaller
}

Push-Location $Root
try {
    & $PyInstaller --clean --noconfirm "TranslaziaFDO.spec"
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE"
    }

    $DataDir = Join-Path $DistApp "data"
    New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
    Copy-Item -Force (Join-Path $Root "data\streams_seed.txt") (Join-Path $DataDir "streams_seed.txt")
    if (Test-Path (Join-Path $Root "data\settings.json")) {
        Copy-Item -Force (Join-Path $Root "data\settings.json") (Join-Path $DataDir "settings.json")
    }

    $VendorTarget = Join-Path $DistApp "vendor"
    if (Test-Path $VendorTarget) {
        Remove-Item -Recurse -Force $VendorTarget
    }
    Copy-Item -Recurse -Force (Join-Path $Root "vendor") $VendorTarget

    Write-Host "Done: $DistApp\TranslaziaFDO.exe"
}
finally {
    Pop-Location
}
