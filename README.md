# opencode-voice-kit

**给 opencode（及任何 Windows 程序）加上「一键说话 + 语音回复」的本地语音方案。**

> Local voice I/O for opencode: a floating push-to-talk button (whisper.cpp) + a
> plugin that speaks the agent's replies aloud (edge-tts). Everything runs on your
> machine — no API keys, no cloud STT.

---

## 它能做什么

```
点一下悬浮按钮  →  说话  →  自动静音停止
                →  本地 whisper.cpp 转写
                →  自动粘贴进当前输入框并回车
                →  AI 回复  →  自动朗读出来
                →  再点一下，继续下一轮
```

这就是「你一言我一语」的语音对话，而且：

- 🔒 **全本地**：语音识别在你电脑上跑，音频不出本机
- 🎤 **免打字**：按住/点一下按钮说话即可
- 🔊 **会说话**：AI 的回复用微软 edge-tts 的中文神经语音念出来（免费）
- 🪟 **Windows 原生**：悬浮窗不抢焦点，粘贴一定落到目标窗口
- 🧩 **不挑程序**：任何有输入框的程序都能用（opencode / 终端 / 编辑器 / 聊天）

## 目录结构

```
opencode-voice-kit/
├── floating-button/            # 悬浮语音按钮（Python + Tkinter）
│   ├── voice_button.py
│   ├── start-voice-button.vbs  # 无控制台启动
│   └── requirements.txt
├── opencode-plugin/            # opencode 语音回复插件（纯 Node）
│   ├── voice-tts.js
│   └── opencode-tts.jsonc.example
├── install.ps1                 # 一键安装脚本
└── README.md
```

---

## 依赖

| 组件 | 用途 | 安装 |
|---|---|---|
| Python 3.10+ | 悬浮按钮 | https://python.org |
| `sounddevice` `numpy` | 录音 | `pip install sounddevice numpy` |
| **whisper.cpp**（`whisper-cli`）+ ggml 模型 | 本地语音识别 | 见下 |
| **ffmpeg**（含 `ffplay`） | 播放 TTS 音频 | `winget install Gyan.FFmpeg` |
| **edge-tts** | 中文语音合成 | `pip install edge-tts` |

### 装 whisper.cpp + 模型（Windows）

最简单：用 [Handy](https://github.com/cjpais/Handy) 的托管引擎（本工具会自动探测）：

```
~/.cache/opencode-voice/engines/whisper.cpp/win32-x64/whisper-cli.exe
~/.cache/opencode-voice/models/ggml-small.bin
```

或者自己下载：

```powershell
# 模型（推荐 small 或 large-v3-turbo）
curl -L -o "$env:USERPROFILE\.cache\opencode-voice\models\ggml-small.bin" `
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin
```

> 没有自动探测到？设置环境变量 `WHISPER_CLI` 和 `WHISPER_MODEL` 指向你的文件即可。

---

## 安装

### 方式一：一键脚本

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

脚本会：安装 pip 依赖 → 复制插件到 `~/.config/opencode/voice/` → 写配置 → 提示你手动加上 plugin 注册项。

### 方式二：手动（推荐，最可控）

**1. 悬浮按钮**

```powershell
cd floating-button
pip install -r requirements.txt
# 双击 start-voice-button.vbs，或：
pythonw voice_button.py
```

**2. opencode 语音回复插件**

```powershell
# 复制插件
mkdir "$env:USERPROFILE\.config\opencode\voice" -Force
copy .\opencode-plugin\voice-tts.js "$env:USERPROFILE\.config\opencode\voice\"

# 复制配置
mkdir "$env:USERPROFILE\.config\opencode\plugins" -Force
copy .\opencode-plugin\opencode-tts.jsonc.example "$env:USERPROFILE\.config\opencode\plugins\opencode-tts.jsonc"

# 装 edge-tts
pip install edge-tts
```

然后编辑 `~/.config/opencode/opencode.json`，在 `plugin` 数组里加一行
（注意：是 **file:// 绝对路径**，Windows 用正斜杠）：

```json
{
  "$schema": "https://opencode.ai/config.json",
  "plugin": [
    "file:///C:/Users/你的用户名/.config/opencode/voice/voice-tts.js"
  ]
}
```

**重启 opencode**，回复就会被朗读。

---

## 使用

| 操作 | 说明 |
|---|---|
| 点悬浮按钮 🎤 | 开始录音（变红），说话，停顿约 1 秒自动结束 |
| 拖动 | 移动按钮位置 |
| 右键 | 退出按钮 |
| 转写结果 | 自动粘贴到当前焦点窗口并回车 |

想让按钮**只填入不发送**？设环境变量 `VOICE_AUTO_ENTER=0`。

## 配置（`~/.config/opencode/plugins/opencode-tts.jsonc`）

```jsonc
{
  "enabled": true,                                  // 总开关
  "voice": "zh-CN-XiaoxiaoNeural",                  // 音色
  "edge_tts": {
    "voice": "zh-CN-XiaoxiaoNeural",
    "rate": "+15%",                                 // 语速
    "volume": "+0%",
    "command": ["python", "-m", "edge_tts"]         // 合成命令
  }
}
```

常用中文音色：

| voice | 说明 |
|---|---|
| `zh-CN-XiaoxiaoNeural` | 晓晓，女声（默认） |
| `zh-CN-YunxiNeural` | 云希，男声 |
| `zh-CN-YunjianNeural` | 云健，男声沉稳 |
| `zh-CN-XiaoyiNeural` | 晓伊，女声活泼 |
| `zh-TW-HsiaoChenNeural` | 台湾腔 |

> ⚠️ **别在配置里写中文注释**：opencode 会自动格式化这个文件，可能把注释和后面的
> 键挤到同一行，导致键被注释掉。用纯 JSON 最稳。

---

## 踩过的坑（重要）

这些是本项目实际调试出来的，能帮你省几小时：

1. **插件用 `command -v` 检测播放器** → Windows 的 Bun shell 不支持，永远失败。
   本仓库的 `voice-tts.js` 已改用 `node:child_process` + `ffplay`，无此问题。
2. **插件不创建日志目录** → `appendFileSync` 静默失败，让你误以为插件没加载。
3. **opencode 格式化吃掉注释** → 见上。
4. **本地插件模式下 `pluginInput.$` 是 `undefined`** → 依赖 Bun shell 的插件会直接崩。
5. **opencode 桌面版没有 UI 插件接口** → 所以「按钮」只能做成悬浮窗；
   桌面版也不加载终端 TUI 插件（`tui.json` 里的 `ctrl+r` 那类）。

---

## License

MIT
