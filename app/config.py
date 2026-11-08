"""配置读写与密钥解析。

配置落在 ~/.dsh/whale-girl/config.json，和 DSH 的 home 放在一起，
卸载插件也不用删它——浮窗自己会读。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

HOME = Path.home()
DSH_HOME = Path(os.environ.get("DSH_HOME", HOME / ".dsh"))
CONFIG_PATH = DSH_HOME / "whale-girl" / "config.json"
CACHE_DIR = DSH_HOME / "whale-girl" / "cache"
LOG_PATH = DSH_HOME / "whale-girl" / "log.jsonl"

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = HOME / ".local" / "share" / "dsh-whale-girl"

DEFAULTS = {
    "endpoint": "http://127.0.0.1:8791",
    # 采样与挑帧
    "sampleIntervalSec": 2.0,
    "diffThreshold": 0.06,
    "minChangedRatio": 0.18,
    "batchSize": 9,
    "minSendIntervalSec": 20,
    "sendMode": "grid",  # grid = 拼成一张九宫格；frames = 九张原图分开发
    # 模型与参考音仅从仓库外固定路径读取。
    "tts": {
        "enabled": True,
        "engine": "local",  # local = 本机基座；cloud = DashScope qwen3-tts-flash
        "local": {
            "python": str(ROOT / ".venv" / "bin" / "python"),
            "worker": str(ROOT / "scripts" / "qwen_tts_worker.py"),
            "model": str(DATA_DIR / "tts-model"),
            "referenceAudio": str(DATA_DIR / "reference.wav"),
            "referenceTextPath": str(DATA_DIR / "reference.txt"),
            "temperature": 0.7,
            "language": "Chinese",
        },
        "fallbackCloud": False,
        "model": "qwen3-tts-flash",
        "voice": "Cherry",
        "baseURL": "https://dashscope.aliyuncs.com",
        "apiKey": "",
        "maxChars": 120,
        "volume": 1.0,
    },
    # 浮窗
    "avatar": {
        "size": 156,
        "mode": "portrait",
        "fullbodySize": 360,
        "expressionsPath": str(CONFIG_PATH.parent / "expressions"),
        "x": 48,
        "y": 240,
        "alwaysOnTop": True,
    },
    "bubbleHideAfterSec": 12,
    "watchEnabled": True,
    "chat": {"sessionId": "", "pending": None, "workspacePath": str(ROOT)},
}

def _deep_merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load() -> dict:
    """读配置；文件不存在就用默认值（并顺手建目录）。"""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    for mode in ("portrait", "fullbody"):
        (CONFIG_PATH.parent / "expressions" / mode).mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        config = _deep_merge(DEFAULTS, {})
        save(config)
        return config
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return _deep_merge(DEFAULTS, {})
    return _deep_merge(DEFAULTS, raw)


def save(config: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def resolve_api_key(config: dict) -> str:
    """密钥只来自显式配置或 DASHSCOPE_API_KEY 环境变量。"""
    tts = config.get("tts", {})
    if tts.get("apiKey"):
        return str(tts["apiKey"]).strip()
    env = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    if env:
        return env
    return ""
