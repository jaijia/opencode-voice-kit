# opencode-voice-kit 安装脚本 (Windows PowerShell)
# 用法: powershell -ExecutionPolicy Bypass -File .\install.ps1
$ErrorActionPreference = "Stop"

function Info($m) { Write-Host "[*] $m" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "[+] $m" -ForegroundColor Green }
function Warn($m) { Write-Host "[!] $m" -ForegroundColor Yellow }

$Root      = Split-Path -Parent $MyInvocation.MyCommand.Path
$Opencode  = Join-Path $env:USERPROFILE ".config\opencode"
$VoiceDir  = Join-Path $Opencode "voice"
$PlugDir   = Join-Path $Opencode "plugins"

Write-Host "`n=== opencode-voice-kit 安装 ===`n" -ForegroundColor White

# 1. Python
Info "检查 Python ..."
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { Warn "找不到 python，请先安装 Python 3.10+ 并加入 PATH"; exit 1 }
Ok "python: $((python --version 2>&1))"

# 2. pip 依赖
Info "安装 Python 依赖 (sounddevice, numpy, edge-tts) ..."
python -m pip install --quiet --upgrade sounddevice numpy edge-tts
Ok "Python 依赖安装完成"

# 3. 复制插件
Info "部署 opencode 语音回复插件 ..."
New-Item -ItemType Directory -Force -Path $VoiceDir, $PlugDir | Out-Null
Copy-Item -Force (Join-Path $Root "opencode-plugin\voice-tts.js") $VoiceDir
Ok "插件 -> $VoiceDir\voice-tts.js"

# 4. 配置（不覆盖已有）
$cfgDst = Join-Path $PlugDir "opencode-tts.jsonc"
if (Test-Path $cfgDst) {
  Warn "配置已存在，跳过: $cfgDst"
} else {
  Copy-Item -Force (Join-Path $Root "opencode-plugin\opencode-tts.jsonc.example") $cfgDst
  Ok "配置 -> $cfgDst"
}

# 5. 注册插件到 opencode.json
$ocJson = Join-Path $Opencode "opencode.json"
$spec   = "file:///" + ($VoiceDir -replace '\\', '/') + "/voice-tts.js"
Info "需要在 opencode.json 注册: $spec"

if (Test-Path $ocJson) {
  Copy-Item -Force $ocJson "$ocJson.bak"
  $raw = Get-Content $ocJson -Raw
  if ($raw -match [regex]::Escape($spec)) {
    Ok "已注册，无需修改"
  } else {
    Warn "请手动把下面这行加入 $ocJson 的 plugin 数组："
    Write-Host "    `"$spec`"" -ForegroundColor Yellow
    Write-Host "  （已备份原文件为 opencode.json.bak）" -ForegroundColor DarkGray
  }
} else {
  Warn "未找到 $ocJson，请手动创建并加入："
  Write-Host "    `"$spec`"" -ForegroundColor Yellow
}

# 6. 环境自检
Write-Host "`n--- 环境自检 ---" -ForegroundColor White
if (Get-Command ffplay -ErrorAction SilentlyContinue) { Ok "ffplay: $((Get-Command ffplay).Source)" }
else { Warn "未找到 ffplay —— 请安装 ffmpeg (winget install Gyan.FFmpeg)" }

$whisper = @(
  (Join-Path $env:USERPROFILE ".cache\opencode-voice\engines"),
  (Join-Path $env:USERPROFILE ".local\share\whisper.cpp")
) | Where-Object { Test-Path $_ } | ForEach-Object {
  Get-ChildItem $_ -Recurse -Filter "whisper-cli*" -ErrorAction SilentlyContinue
} | Select-Object -First 1
if ($whisper) { Ok "whisper-cli: $($whisper.FullName)" }
else { Warn "未找到 whisper-cli —— 请设置 WHISPER_CLI 环境变量，或安装 Handy / 自行编译 whisper.cpp" }

Write-Host "`n=== 完成 ===" -ForegroundColor Green
Write-Host "1) 启动悬浮按钮: 双击 floating-button\start-voice-button.vbs" -ForegroundColor White
Write-Host "2) 重启 opencode 使语音回复插件生效" -ForegroundColor White
Write-Host "3) 调音色/语速: 编辑 $cfgDst" -ForegroundColor White
