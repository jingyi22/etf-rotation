# ETF 轮动 · 开盘复核计划任务（工作日 09:26 由 Windows 计划任务调起）
# 行情获取失败（退出码 2）时每 60 秒重试，最多 8 次；日志写到 %LOCALAPPDATA%\etf-rotation\open_review.log
$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
$Py = "D:\Users\elenalu\AppData\Local\Programs\Python\Python313\python.exe"
$LogDir = Join-Path $env:LOCALAPPDATA "etf-rotation"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log = Join-Path $LogDir "open_review.log"
if ((Test-Path $Log) -and ((Get-Item $Log).Length -gt 1MB)) { Move-Item -Force $Log "$Log.1" }

$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8   # 否则 PowerShell 按 GBK 解码 python 输出，日志乱码
Set-Location $Repo
Add-Content -Path $Log -Value ("==== " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss") + " start") -Encoding UTF8
for ($i = 1; $i -le 8; $i++) {
    $out = & $Py "scripts\open_review.py" 2>&1
    $code = $LASTEXITCODE
    Add-Content -Path $Log -Value ($out -join "`n") -Encoding UTF8
    if ($code -ne 2) { break }
    Add-Content -Path $Log -Value "  行情获取失败，60 秒后重试（第 $i 次）" -Encoding UTF8
    Start-Sleep -Seconds 60
}
Add-Content -Path $Log -Value ("==== " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss") + " exit $code") -Encoding UTF8
