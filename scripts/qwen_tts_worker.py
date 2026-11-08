#!/usr/bin/env python3
"""常驻的 Qwen3-TTS 本地合成进程（stdin/stdout JSON 行协议）。

为什么不每次起一个新进程：模型加载要 8 秒、常驻内存 8GB 上下，
每说一句话重来一次就没法用了。这里加载一次，然后一行一条请求。

协议：
  启动后第一行输出  {"ready": true, "model": "...", "sample_rate": 24000}
  之后每行输入      {"id": "...", "text": "...", "out": "/abs/out.wav"}
  每行输出          {"id": "...", "ok": true, "path": "...", "seconds": 1.2}
                    {"id": "...", "ok": false, "error": "..."}

用本项目 .venv 里的 python 跑（uv.lock 锁定 mlx_audio）：
  .venv/bin/python scripts/qwen_tts_worker.py \
      --model ~/.cache/.../snapshots/<rev> \
      --ref-audio <reference.wav> \
      --ref-text '<参考音的准确台词>'
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import wave
from pathlib import Path

import numpy as np


# 协议行加前缀：mlx_audio / transformers 在加载时会把日志打到 stdout，
# 不加标记的话客户端第一行读到的是 "Loaded speech tokenizer..."，JSON 直接炸。
SENTINEL = "__WHALE_TTS__"


def proto(payload: dict) -> None:
    print(SENTINEL + " " + json.dumps(payload, ensure_ascii=False), flush=True)


def write_wav(path: Path, samples: np.ndarray, sample_rate: int) -> float:
    """float32 [-1,1] -> 16bit PCM wav，返回时长秒数。"""
    clipped = np.clip(samples, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())
    return len(pcm) / float(sample_rate)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, help="模型快照目录")
    parser.add_argument("--ref-audio", required=True, help="参考音色 wav")
    parser.add_argument("--ref-text", required=True, help="参考音色对应的台词")
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--language", default="Chinese")
    parser.add_argument("--max-tokens", type=int, default=4096)
    args = parser.parse_args()

    from mlx_audio.tts import load_model

    started = time.time()
    model = load_model(Path(args.model).expanduser())
    load_seconds = time.time() - started

    proto({"ready": True, "model": str(args.model), "load_seconds": round(load_seconds, 2)})

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as error:
            proto({"ok": False, "error": f"bad json: {error}"})
            continue

        request_id = request.get("id")
        text = str(request.get("text", "")).strip()
        out = request.get("out")
        if not text or not out:
            proto({"id": request_id, "ok": False, "error": "text/out 都是必填"})
            continue

        began = time.time()
        try:
            chunks = []
            sample_rate = 24000
            for result in model.generate(
                text=text,
                ref_audio=str(Path(args.ref_audio).expanduser()),
                ref_text=args.ref_text,
                lang_code=args.language,
                temperature=float(request.get("temperature", args.temperature)),
                speed=float(request.get("speed", 1.0)),
                max_tokens=int(request.get("max_tokens", args.max_tokens)),
            ):
                chunks.append(np.array(result.audio).reshape(-1))
                sample_rate = int(result.sample_rate)
            if not chunks:
                raise RuntimeError("模型没有产出音频")
            audio = np.concatenate(chunks)
            seconds = write_wav(Path(out), audio, sample_rate)
            proto(
                {
                    "id": request_id,
                    "ok": True,
                    "path": out,
                    "seconds": round(seconds, 2),
                    "generation_seconds": round(time.time() - began, 2),
                }
            )
        except Exception as error:  # 一条失败不该带走整个进程
            proto({"id": request_id, "ok": False, "error": str(error)[:400]})

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
