// opencode 语音回复插件
// ====================
// 监听 session.idle -> 取最后一条助手回复 -> edge-tts 合成 -> ffplay 播放
//
// 特点：
//   - 纯 Node API（child_process），不依赖 Bun shell，Windows / macOS / Linux 通用
//   - 配置文件：~/.config/opencode/plugins/opencode-tts.jsonc
//   - 日志（debug=true 时）：~/.config/opencode/logs/opencode-tts.log
//
// 安装：把本文件放到 ~/.config/opencode/voice/voice-tts.js，
//       然后在 ~/.config/opencode/opencode.json 的 plugin 数组加入：
//         "file:///C:/Users/你的用户名/.config/opencode/voice/voice-tts.js"
//       （macOS/Linux： "file:///Users/你的用户名/.config/opencode/voice/voice-tts.js"）
import os from "node:os";
import path from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { readFileSync, appendFileSync, mkdirSync, unlinkSync } from "node:fs";

const pExecFile = promisify(execFile);
const OPENCODE_DIR = path.join(os.homedir(), ".config", "opencode");
const CONFIG_PATH = path.join(OPENCODE_DIR, "plugins", "opencode-tts.jsonc");
const LOG_PATH = path.join(OPENCODE_DIR, "logs", "opencode-tts.log");

const DEFAULTS = {
  voice: "zh-CN-XiaoxiaoNeural",
  rate: "+15%",
  volume: "+0%",
  command: ["python", "-m", "edge_tts"],
  maxChars: 3000,
};

// 播放器：优先用 FFPLAY 环境变量，否则用 PATH 里的 ffplay
const FFPLAY = process.env.FFPLAY || "ffplay";

function readConfig() {
  try {
    const raw = readFileSync(CONFIG_PATH, "utf8")
      .replace(/\/\/.*$/gm, "")
      .replace(/\/\*[\s\S]*?\*\//g, "");
    return JSON.parse(raw);
  } catch {
    return {};
  }
}

function log(msg, extra) {
  try {
    if (!readConfig().debug) return;
    mkdirSync(path.dirname(LOG_PATH), { recursive: true });
    const suffix = extra === undefined ? "" : " " + JSON.stringify(extra);
    appendFileSync(LOG_PATH, `${new Date().toISOString()} ${msg}${suffix}\n`);
  } catch {
    /* 日志失败绝不能影响朗读 */
  }
}

function clean(value) {
  return String(value ?? "")
    .replace(/<think>[\s\S]*?<\/think>/gi, " ")
    .replace(/<reflection>[\s\S]*?<\/reflection>/gi, " ")
    .replace(/```[\s\S]*?```/g, " 代码块 ")
    .replace(/\s+/g, " ")
    .trim();
}

const lastAssistant = new Map(); // sessionID -> messageID
const textByMessage = new Map(); // messageID -> text
const spoken = new Set(); // messageID
const inFlight = new Set(); // sessionID

async function speak(text) {
  const cfg = readConfig();
  const voice = cfg.voice || cfg.edge_tts?.voice || DEFAULTS.voice;
  const rate = cfg.edge_tts?.rate || DEFAULTS.rate;
  const volume = cfg.edge_tts?.volume || DEFAULTS.volume;
  const cmd = cfg.edge_tts?.command?.length ? cfg.edge_tts.command : DEFAULTS.command;
  const say = text.slice(0, cfg.maxChars || DEFAULTS.maxChars);

  const mp3 = path.join(os.tmpdir(), `opencode-tts-${Date.now()}.mp3`);
  log("tts.start", { voice, rate, chars: say.length, mp3 });
  try {
    await pExecFile(
      cmd[0],
      [...cmd.slice(1), "--voice", voice, "--rate", rate, "--volume", volume,
        "--text", say, "--write-media", mp3],
      { windowsHide: true, timeout: 120000 },
    );
    log("tts.generated", { mp3 });
    await pExecFile(FFPLAY, ["-nodisp", "-autoexit", "-loglevel", "quiet", mp3],
      { windowsHide: true, timeout: 600000 });
    log("tts.played", { mp3 });
  } finally {
    try { unlinkSync(mp3); } catch { /* ignore */ }
  }
}

export const VoiceTTSPlugin = async () => {
  log("plugin.loaded");
  return {
    event: async ({ event }) => {
      try {
        if (!event || !event.type) return;
        const props = event.properties || {};

        if (event.type === "message.updated") {
          const info = props.info;
          if (info && info.role === "assistant" && info.sessionID && info.id) {
            lastAssistant.set(info.sessionID, info.id);
          }
          return;
        }

        if (event.type === "message.part.updated") {
          const part = props.part;
          if (part && part.type === "text" && part.messageID) {
            textByMessage.set(part.messageID, part.text ?? "");
          }
          return;
        }

        if (event.type !== "session.idle") return;
        if (readConfig().enabled === false) return; // 总开关
        const sessionID = props.sessionID;
        if (!sessionID || inFlight.has(sessionID)) return;

        const messageID = lastAssistant.get(sessionID);
        if (!messageID || spoken.has(messageID)) return;

        const text = clean(textByMessage.get(messageID));
        if (!text) return;

        inFlight.add(sessionID);
        spoken.add(messageID);
        try {
          await speak(text);
          log("tts.done", { sessionID, messageID });
        } finally {
          inFlight.delete(sessionID);
        }
      } catch (err) {
        log("tts.error", { message: String(err?.message ?? err) });
      }
    },
  };
};

export default VoiceTTSPlugin;
