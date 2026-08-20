$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

# Keep this script ASCII-only so Windows PowerShell 5.1 cannot decode the app
# name with the active ANSI code page. U+6570 U+636E U+5DE5 U+574A = Data Workbench.
$AppName = -join ([char[]](0x6570, 0x636E, 0x5DE5, 0x574A))
$LegacyMojibakeName = -join ([char[]](37825, 29256, 23873, 23480, 12517, 28497))

# Remove only the exact legacy artifacts produced by the old mis-decoded name.
$LegacyGeneratedTargets = @(
    (Join-Path (Join-Path $ProjectRoot 'build') $LegacyMojibakeName),
    (Join-Path (Join-Path $ProjectRoot 'dist') $LegacyMojibakeName)
)
foreach ($Target in $LegacyGeneratedTargets) {
    $FullTarget = [IO.Path]::GetFullPath($Target)
    if (-not $FullTarget.StartsWith([IO.Path]::GetFullPath($ProjectRoot), [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to clean a generated path outside the project root: $FullTarget"
    }
    if (Test-Path -LiteralPath $FullTarget) { Remove-Item -LiteralPath $FullTarget -Recurse -Force }
}
$LegacySpec = Join-Path $ProjectRoot "$LegacyMojibakeName.spec"
if (Test-Path -LiteralPath $LegacySpec) { Remove-Item -LiteralPath $LegacySpec -Force }

Push-Location (Join-Path $ProjectRoot 'frontend')
try {
    npm ci --prefer-offline --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw "Frontend dependency installation failed with exit code $LASTEXITCODE" }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend build failed with exit code $LASTEXITCODE" }
}
finally {
    Pop-Location
}

$VenvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$Python = if (Test-Path $VenvPython) { $VenvPython } else { 'python' }

& $Python -m pip install -r (Join-Path $ProjectRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw "Python dependency installation failed with exit code $LASTEXITCODE" }
& $Python -m PyInstaller --noconfirm --clean --windowed --name $AppName `
    --icon (Join-Path $ProjectRoot 'assets\data-workbench.ico') `
    --paths (Join-Path $ProjectRoot 'backend') `
    --add-data "$(Join-Path $ProjectRoot 'backend');backend" `
    --add-data "$(Join-Path $ProjectRoot 'frontend\dist\client');frontend/dist/client" `
    --collect-all webview `
    (Join-Path $ProjectRoot 'app.py')
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }

$AppDist = Join-Path (Join-Path $ProjectRoot 'dist') $AppName
$PluginTarget = Join-Path $AppDist 'plugins_external'
New-Item -ItemType Directory -Force -Path $PluginTarget | Out-Null
Copy-Item -Recurse -Force -Path (Join-Path $ProjectRoot 'plugins_external\*') -Destination $PluginTarget

$Executable = Join-Path $AppDist "$AppName.exe"
if (-not (Test-Path -LiteralPath $Executable)) { throw "Expected executable was not created: $Executable" }
Write-Host "Build complete: $Executable"
