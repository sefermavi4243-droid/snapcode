# Builds build\dist\SnapCode\SnapCode.exe and build\installer\SnapCode-Setup-<version>.exe
# Usage: powershell -ExecutionPolicy Bypass -File packaging\build.ps1 [-SkipSelfTest]
param([switch]$SkipSelfTest)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$version = (Select-String -Path "snapcode\__init__.py" -Pattern '__version__ = "(.+)"').Matches[0].Groups[1].Value
Write-Host "SnapCode $version"

python packaging\make_icon.py
if ($LASTEXITCODE) { throw "icon failed" }

if (Test-Path build\dist) { Remove-Item -Recurse -Force build\dist }
python -m PyInstaller packaging\snapcode.spec --noconfirm --distpath build\dist --workpath build\work
if ($LASTEXITCODE) { throw "PyInstaller failed" }

# Prove the frozen exe can still reach Windows OCR before shipping it.
if (-not $SkipSelfTest) {
    $out = Join-Path $env:TEMP "snapcode-selftest.txt"
    $p = Start-Process build\dist\SnapCode\SnapCode.exe -ArgumentList "--selftest", $out -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw "self-test failed: $(Get-Content $out -Raw)" }
    Write-Host "self-test ok"
}

$iscc = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 not found (winget install JRSoftware.InnoSetup)" }

& $iscc /Q "/DAppVersion=$version" packaging\installer.iss
if ($LASTEXITCODE) { throw "ISCC failed" }
Get-ChildItem build\installer\*.exe | ForEach-Object { "{0}  {1:N1} MB" -f $_.FullName, ($_.Length / 1MB) }
