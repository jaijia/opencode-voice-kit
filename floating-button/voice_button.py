"""
opencode / 通用 语音对话悬浮按钮
================================
一个始终置顶的小窗口，点一下就能说话：

    点击 🎤  ->  录音（检测到静音自动停止）
              ->  本地 whisper.cpp 转写
              ->  自动粘贴到当前焦点窗口并回车

配合 opencode-tts 插件（见 opencode-plugin/），AI 的回复会被朗读出来，
形成「你一言我一语」的语音对话。

窗口使用 WS_EX_NOACTIVATE，点击不会抢走目标程序的焦点，保证粘贴正确。

依赖：
    pip install sounddevice numpy
    ffmpeg（用于把音频转成 whisper 需要的格式；可选，见 README）
    whisper.cpp 的 whisper-cli 可执行文件 + 一个 ggml 模型

环境变量（可选，覆盖自动探测）：
    WHISPER_CLI       whisper-cli(.exe) 的完整路径
    WHISPER_MODEL     ggml 模型(.bin/.gguf) 的完整路径
    VOICE_LANG        识别语言，默认 zh（auto=自动）
    VOICE_AUTO_ENTER  1/0，转写后是否自动回车发送，默认 1
"""
import ctypes
import os
import shutil
import subprocess
import tempfile
import threading
import time
import wave

import numpy as np
import sounddevice as sd
import tkinter as tk

# ---------------- 可调参数 ----------------
RATE = 16000           # 采样率（whisper 要求 16k）
CHUNK = 480            # 每块 30ms
SILENCE_DB = -40       # 静音阈值(dB)，环境嘈杂可调到 -35
SILENCE_SEC = 1.1      # 连续静音多久算说完
MAX_SEC = 30           # 单次最长录音秒数
MIN_SEC = 0.6          # 低于这个时长视为误触
# -----------------------------------------

LANG = os.environ.get("VOICE_LANG", "zh")
AUTO_ENTER = os.environ.get("VOICE_AUTO_ENTER", "1") != "0"

VK_CONTROL, VK_V, VK_RETURN = 0x11, 0x56, 0x0D
GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080


def log(msg):
    print(msg, flush=True)


# ------------------------- 定位 whisper -------------------------
def find_whisper():
    """按优先级查找 whisper-cli 可执行文件。"""
    env = os.environ.get("WHISPER_CLI")
    if env and os.path.isfile(env):
        return env

    names = {"whisper-cli.exe", "whisper-cli", "main.exe", "main"}
    roots = [
        os.path.join(os.path.expanduser("~"), ".cache", "opencode-voice", "engines"),
        os.path.join(os.path.expanduser("~"), ".local", "share", "whisper.cpp"),
        os.path.join(os.path.expanduser("~"), "whisper.cpp"),
    ]
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dirpath, _dirs, files in os.walk(root):
            for f in files:
                if f.lower() in names:
                    return os.path.join(dirpath, f)

    for n in ("whisper-cli", "whisper-cli.exe", "main"):
        found = shutil.which(n)
        if found:
            return found
    return None


def find_model():
    """查找 ggml 模型，优先 turbo / large / medium。"""
    env = os.environ.get("WHISPER_MODEL")
    if env and os.path.isfile(env):
        return env

    dirs = [
        os.path.join(os.path.expanduser("~"), ".cache", "opencode-voice", "models"),
        os.path.join(os.path.expanduser("~"), ".local", "share", "whisper-cpp"),
        os.path.join(os.path.expanduser("~"), ".local", "share", "whisper.cpp"),
    ]

    def rank(name):
        low = name.lower()
        if "turbo" in low:
            return 0
        if "large" in low:
            return 1
        if "medium" in low:
            return 2
        if "small" in low:
            return 3
        return 4

    for d in dirs:
        if not os.path.isdir(d):
            continue
        bins = [f for f in os.listdir(d) if f.lower().endswith((".bin", ".gguf"))]
        if bins:
            bins.sort(key=lambda n: (rank(n), n))
            return os.path.join(d, bins[0])
    return None


# ------------------------- 录音 / 转写 -------------------------
def record_to(path):
    """录音，检测到静音自动停止，写出 16k 单声道 WAV。返回时长(秒)。"""
    frames = []
    silent = 0
    with sd.InputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=CHUNK) as stream:
        while True:
            data, _ = stream.read(CHUNK)
            frames.append(data)
            rms = float(np.sqrt(np.mean(data.astype(np.float32) ** 2))) / 32768.0
            db = 20 * np.log10(rms + 1e-9)
            silent = silent + 1 if db < SILENCE_DB else 0
            dur = len(frames) * CHUNK / RATE
            if silent * CHUNK / RATE >= SILENCE_SEC and dur > MIN_SEC:
                break
            if dur >= MAX_SEC:
                break

    audio = np.concatenate(frames).flatten()
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(audio.tobytes())
    return len(audio) / RATE


def transcribe(path, whisper, model):
    """调用本地 whisper-cli 转写，返回文本。"""
    cmd = [whisper, "-m", model, "-f", path, "-l", LANG, "-nt"]
    out = subprocess.run(cmd, capture_output=True, text=True,
                         encoding="utf-8", errors="replace", timeout=180)
    text = (out.stdout or "").strip()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return lines[-1] if lines else ""


# ------------------------- 模拟按键 -------------------------
def _key(vk, up=False):
    ctypes.windll.user32.keybd_event(vk, 0, 2 if up else 0, 0)


def paste_and_enter():
    """把剪贴板内容粘贴到当前焦点窗口，并按需回车。"""
    _key(VK_CONTROL)
    _key(VK_V)
    _key(VK_V, True)
    _key(VK_CONTROL, True)
    time.sleep(0.15)
    if AUTO_ENTER:
        _key(VK_RETURN)
        _key(VK_RETURN, True)


# ------------------------- 界面 -------------------------
class VoiceButton:
    def __init__(self):
        self.busy = False
        self.whisper = find_whisper()
        self.model = find_model()

        self.root = tk.Tk()
        self.root.title("语音对话")
        self.root.geometry("170x170+40+320")
        self.root.attributes("-topmost", True)
        self.root.overrideredirect(True)
        self.root.configure(bg="#1e1e2e")

        self.status = tk.Label(self.root, text="语音对话", bg="#1e1e2e", fg="#cdd6f4",
                               font=("Microsoft YaHei", 10))
        self.status.pack(pady=(8, 4))

        self.btn = tk.Button(self.root, text="🎤\n说话", font=("Microsoft YaHei", 16, "bold"),
                             bg="#89b4fa", fg="#1e1e2e", activebackground="#74c7ec",
                             relief="flat", command=self.on_click, cursor="hand2")
        self.btn.pack(expand=True, fill="both", padx=10, pady=(0, 6))

        hint = tk.Label(self.root, text="拖动可移动 · 右键退出", bg="#1e1e2e", fg="#6c7086",
                        font=("Microsoft YaHei", 7))
        hint.pack(pady=(0, 6))

        self.root.bind("<ButtonPress-1>", self.drag_start)
        self.root.bind("<B1-Motion>", self.drag_move)
        self.root.bind("<Button-3>", lambda e: self.root.destroy())

        self.root.after(100, self.make_non_activating)
        self.root.after(200, self.check_env)

    def check_env(self):
        if not self.whisper or not self.model:
            missing = []
            if not self.whisper:
                missing.append("whisper-cli")
            if not self.model:
                missing.append("模型")
            self.set_status("缺少: " + ",".join(missing), "#f38ba8")
            log("找不到 whisper-cli 或模型，请设置 WHISPER_CLI / WHISPER_MODEL 环境变量")
        else:
            log("whisper: %s" % self.whisper)
            log("model  : %s" % self.model)

    def make_non_activating(self):
        """加上 WS_EX_NOACTIVATE，点击不抢焦点（保证粘贴到目标窗口）。"""
        try:
            hwnd = ctypes.windll.user32.GetAncestor(self.root.winfo_id(), 2) or self.root.winfo_id()
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)
        except Exception as e:  # pragma: no cover
            log("non-activating failed: %s" % e)

    def drag_start(self, e):
        self._dx, self._dy = e.x, e.y

    def drag_move(self, e):
        self.root.geometry("+%d+%d" % (self.root.winfo_x() + e.x - self._dx,
                                       self.root.winfo_y() + e.y - self._dy))

    def set_status(self, text, color="#cdd6f4"):
        self.status.config(text=text, fg=color)

    def on_click(self):
        if self.busy:
            return
        if not self.whisper or not self.model:
            self.set_status("缺 whisper/模型，见 README", "#f38ba8")
            return
        self.busy = True
        self.btn.config(bg="#f38ba8", text="●\n录音中")
        self.set_status("录音中… 说完停顿 1 秒", "#f38ba8")
        threading.Thread(target=self.work, daemon=True).start()

    def work(self):
        tmp = os.path.join(tempfile.gettempdir(), "voice-button-rec.wav")
        try:
            record_to(tmp)
            self.set_status("转写中…", "#f9e2af")
            text = transcribe(tmp, self.whisper, self.model)
            if not text:
                self.set_status("没听清，再试一次", "#f38ba8")
                return
            log("transcript: %s" % text)
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.root.update()
            time.sleep(0.05)
            paste_and_enter()
            self.set_status("已发送：" + text[:14], "#a6e3a1")
        except Exception as e:
            log("error: %s" % e)
            self.set_status("出错：" + str(e)[:18], "#f38ba8")
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
            self.busy = False
            self.btn.config(bg="#89b4fa", text="🎤\n说话")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    VoiceButton().run()
