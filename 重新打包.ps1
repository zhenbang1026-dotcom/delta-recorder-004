$ErrorActionPreference = "Stop"

$项目目录 = Split-Path -Parent $MyInvocation.MyCommand.Path
$构建脚本 = Join-Path $项目目录 "build_nuitka.ps1"
$发布目录 = Join-Path $项目目录 "发布\005_nuitka\主界面.dist"
$发布程序 = Join-Path $发布目录 "三角洲录制器005.exe"

if (-not (Test-Path -LiteralPath $构建脚本 -PathType Leaf)) {
    throw "未找到 Nuitka 构建脚本：$构建脚本"
}

Write-Host "开始重新打包三角洲录制器005（Nuitka standalone）..." -ForegroundColor Cyan
& $构建脚本
if ($LASTEXITCODE -ne 0) {
    throw "重新打包失败，退出码：$LASTEXITCODE"
}

if (-not (Test-Path -LiteralPath $发布程序 -PathType Leaf)) {
    throw "重新打包完成但未找到程序：$发布程序"
}

$源码扩展名 = @(".py", ".pyc", ".pyo", ".pyi", ".c", ".h", ".o", ".obj")
$源码文件 = @(
    Get-ChildItem -LiteralPath $发布目录 -Recurse -File |
        Where-Object { $_.Extension.ToLowerInvariant() -in $源码扩展名 }
)
if ($源码文件.Count -gt 0) {
    $源码列表 = ($源码文件.FullName -join [Environment]::NewLine)
    throw "发布目录中发现源码或编译中间文件：$([Environment]::NewLine)$源码列表"
}

Write-Host "重新打包完成：$发布程序" -ForegroundColor Green
Write-Host "已检查：发布目录不包含 Python 源码和 C 编译中间文件。" -ForegroundColor Green
