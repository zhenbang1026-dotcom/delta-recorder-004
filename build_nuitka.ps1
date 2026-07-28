param(
    [switch]$保留临时源码
)

$ErrorActionPreference = "Stop"
$项目目录 = Split-Path -Parent $MyInvocation.MyCommand.Path
$构建环境 = Join-Path $env:SystemDrive "delta_recorder_005_nuitka_venv"
$Python = Join-Path $构建环境 "Scripts\python.exe"
$输出目录 = Join-Path $项目目录 "发布\005_nuitka"
$临时根目录 = Join-Path $env:SystemDrive "delta_recorder_005_nuitka_source"
$临时项目目录 = Join-Path $临时根目录 "app"

if (-not (Test-Path -LiteralPath $Python)) {
    $系统Python = Get-Command python -ErrorAction SilentlyContinue
    if ($null -eq $系统Python) {
        throw "未找到 Python，无法创建 Nuitka 打包环境。"
    }
    & $系统Python.Source -m venv $构建环境
    & $Python -m pip install -r (Join-Path $项目目录 "requirements.txt") nuitka
}

foreach ($必需文件 in @("动作代码块.json", "best.onnx")) {
    if (-not (Test-Path -LiteralPath (Join-Path $项目目录 $必需文件))) {
        throw "缺少打包必需文件：$必需文件"
    }
}

if (Test-Path -LiteralPath $临时根目录) {
    Remove-Item -LiteralPath $临时根目录 -Recurse -Force
}
New-Item -ItemType Directory -Path $临时项目目录 -Force | Out-Null

# Nuitka 的 Windows DLL 分析器对中文目录兼容性不好，先复制到 ASCII 路径构建。
Get-ChildItem -LiteralPath $项目目录 -File -Filter "*.py" |
    Copy-Item -Destination $临时项目目录 -Force

foreach ($相对路径 in @(
    "动作代码块.json",
    "best.onnx",
    "maps",
    "校准截图",
    "校准截图黄色",
    "校准截图蓝色",
    "校准截图绿色"
)) {
    $源 = Join-Path $项目目录 $相对路径
    $目标 = Join-Path $临时项目目录 $相对路径
    if (Test-Path -LiteralPath $源 -PathType Container) {
        New-Item -ItemType Directory -Path $目标 -Force | Out-Null
        Copy-Item -Path (Join-Path $源 "*") -Destination $目标 -Recurse -Force
    } else {
        Copy-Item -LiteralPath $源 -Destination $目标 -Force
    }
}

if (Test-Path -LiteralPath $输出目录) {
    Remove-Item -LiteralPath $输出目录 -Recurse -Force
}
New-Item -ItemType Directory -Path $输出目录 -Force | Out-Null

$参数 = @(
    "--standalone",
    "--follow-imports",
    "--enable-plugin=tk-inter",
    "--windows-console-mode=disable",
    "--output-dir=$输出目录",
    "--output-filename=三角洲录制器005.exe"
)

foreach ($模块名 in @(
    "A测试角度识别",
    "A测试模版匹配",
    "识别角度",
    "截图模块",
    "A记录坐标和角度版本",
    "Win32键鼠模块"
)) {
    $参数 += "--include-module=$模块名"
}

$参数 += "--include-data-dir=$(Join-Path $临时项目目录 'maps')=maps"
$参数 += "--include-data-dir=$(Join-Path $临时项目目录 '校准截图')=校准截图"
$参数 += "--include-data-dir=$(Join-Path $临时项目目录 '校准截图黄色')=校准截图黄色"
$参数 += "--include-data-dir=$(Join-Path $临时项目目录 '校准截图蓝色')=校准截图蓝色"
$参数 += "--include-data-dir=$(Join-Path $临时项目目录 '校准截图绿色')=校准截图绿色"
$参数 += "--include-data-files=$(Join-Path $临时项目目录 '动作代码块.json')=动作代码块.json"
$参数 += "--include-data-files=$(Join-Path $临时项目目录 'best.onnx')=best.onnx"
$参数 += (Join-Path $临时项目目录 "主界面.py")

try {
    & $Python -m nuitka @参数
    if ($LASTEXITCODE -ne 0) {
        throw "Nuitka 打包失败，退出码：$LASTEXITCODE"
    }
} finally {
    if (-not $保留临时源码 -and (Test-Path -LiteralPath $临时根目录)) {
        Remove-Item -LiteralPath $临时根目录 -Recurse -Force
    }
}

$发布目录 = Join-Path $输出目录 "主界面.dist"
$发布程序 = Join-Path $发布目录 "三角洲录制器005.exe"
if (-not (Test-Path -LiteralPath $发布程序)) {
    throw "打包完成但未找到发布程序：$发布程序"
}

$代码块 = Join-Path $发布目录 "动作代码块.json"
if (-not (Test-Path -LiteralPath $代码块)) {
    throw "打包完成但未找到动作代码块：$代码块"
}

Write-Host "打包完成：$发布程序"
Write-Host "动作代码块：$代码块"
