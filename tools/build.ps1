# 一键重新打包 + 安装 + 重启
#
# 用法（在项目根目录，用系统自带的 Windows PowerShell 即可）：
#   powershell -ExecutionPolicy Bypass -File tools\build.ps1
#   powershell -ExecutionPolicy Bypass -File tools\build.ps1 -NoInstall   # 只打包
#
# 说明：这里刻意不用 $ErrorActionPreference='Stop' 包住原生命令 ——
# Windows PowerShell 5.1 会把 PyInstaller 写到 stderr 的日志当成终止性错误。

param(
    [switch]$NoInstall,
    [string]$VenvPython = "$env:LOCALAPPDATA\MouseWheel\venv\Scripts\python.exe"
)

$Proj = Split-Path -Parent $PSScriptRoot
$Build = "$env:LOCALAPPDATA\MouseWheel\build"
$Dest = "$env:LOCALAPPDATA\Programs\FLO-Wheel"

if (-not (Test-Path $VenvPython)) {
    Write-Host "找不到 venv Python：$VenvPython" -ForegroundColor Red
    Write-Host "请先按 README「开发」一节创建环境。" -ForegroundColor Red
    exit 1
}

$env:PYTHONPATH = "$Proj\src"
$env:PYTHONIOENCODING = 'utf-8'

function Invoke-Native {
    param([string[]]$ArgList, [string]$Label)
    $old = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & $VenvPython @ArgList 2>&1 | Out-Null
    $code = $LASTEXITCODE
    $ErrorActionPreference = $old
    if ($code -ne 0) {
        Write-Host "$Label 失败（返回码 $code）" -ForegroundColor Red
        exit 1
    }
}

Write-Host "== 1/4 生成图标 ==" -ForegroundColor Cyan
Invoke-Native -ArgList @("$Proj\tools\make_icon.py") -Label "生成图标"

Write-Host "== 2/4 打包 ==" -ForegroundColor Cyan
Get-Process FLO-Wheel -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Milliseconds 400

$pyiArgs = @(
    '-m', 'PyInstaller', '--noconfirm', '--clean', '--windowed', '--onedir',
    '--name', 'FLO-Wheel',
    '--icon', "$Proj\assets\MouseWheel.ico",
    '--distpath', "$Build\dist",
    '--workpath', "$Build\work",
    '--specpath', "$Build",
    '--paths', "$Proj\src",
    '--exclude-module', 'PySide6.QtQml',
    '--exclude-module', 'PySide6.QtQuick',
    '--exclude-module', 'PySide6.QtQuickWidgets',
    '--exclude-module', 'PySide6.QtWebEngineCore',
    '--exclude-module', 'PySide6.QtWebEngineWidgets',
    '--exclude-module', 'PySide6.QtMultimedia',
    '--exclude-module', 'PySide6.QtMultimediaWidgets',
    '--exclude-module', 'PySide6.Qt3DCore',
    '--exclude-module', 'PySide6.QtCharts',
    '--exclude-module', 'PySide6.QtDataVisualization',
    '--exclude-module', 'PySide6.QtSql',
    '--exclude-module', 'PySide6.QtTest',
    '--exclude-module', 'tkinter',
    "$Proj\launcher.py"
)
Invoke-Native -ArgList $pyiArgs -Label "打包"

$sum = (Get-ChildItem "$Build\dist\FLO-Wheel" -Recurse -File | Measure-Object -Property Length -Sum).Sum
Write-Host ("    产物 {0:N1} MB" -f ($sum / 1MB)) -ForegroundColor Green

if ($NoInstall) {
    Write-Host "== 跳过安装 ==" -ForegroundColor Yellow
    exit 0
}

Write-Host "== 3/4 安装到 $Dest ==" -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $Dest | Out-Null
Copy-Item "$Build\dist\FLO-Wheel\*" $Dest -Recurse -Force

Write-Host "== 4/4 启动 ==" -ForegroundColor Cyan
Start-Process -FilePath (Join-Path $Dest 'FLO-Wheel.exe') -WorkingDirectory $Dest
Start-Sleep -Milliseconds 1800
$proc = Get-Process FLO-Wheel -ErrorAction SilentlyContinue
if ($proc) {
    Write-Host "    已在运行（PID $($proc.Id)）" -ForegroundColor Green
} else {
    Write-Host "    启动失败，请查看 $env:LOCALAPPDATA\MouseWheel\logs\mousewheel.log" -ForegroundColor Red
}
