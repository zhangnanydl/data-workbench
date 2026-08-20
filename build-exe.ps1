$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

Push-Location (Join-Path $ProjectRoot 'frontend')
try {
    npm install --prefer-offline --no-audit --no-fund
    npm run build
}
finally {
    Pop-Location
}

$VenvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$Python = if (Test-Path $VenvPython) { $VenvPython } else { 'python' }

& $Python -m pip install -r (Join-Path $ProjectRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw "依赖安装失败，退出码 $LASTEXITCODE" }
& $Python -m PyInstaller --noconfirm --clean --windowed --name '数据工坊' `
    --icon (Join-Path $ProjectRoot 'assets\data-workbench.ico') `
    --paths (Join-Path $ProjectRoot 'backend') `
    --add-data "$(Join-Path $ProjectRoot 'backend');backend" `
    --add-data "$(Join-Path $ProjectRoot 'frontend\dist\client');frontend/dist/client" `
    --collect-all webview `
    (Join-Path $ProjectRoot 'app.py')
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 构建失败，退出码 $LASTEXITCODE" }

$PluginTarget = Join-Path $ProjectRoot 'dist\数据工坊\plugins_external'
New-Item -ItemType Directory -Force -Path $PluginTarget | Out-Null
Copy-Item -Recurse -Force -Path (Join-Path $ProjectRoot 'plugins_external\*') -Destination $PluginTarget

Write-Host "构建完成：$(Join-Path $ProjectRoot 'dist\数据工坊\数据工坊.exe')"
