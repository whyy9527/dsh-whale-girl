"""Qwen TTS：把一句吐槽念出来。

两条路，按 `tts.engine` 选：

- `local`（默认，也是 DeepSeek 的固定声线）：本机 Qwen3-TTS-12Hz-1.7B-Base-bf16，
  用用户提供的参考音做 ICL 条件，走本项目锁定的 mlx_audio 环境。
  模型加载一次常驻，之后一句一条 JSON 请求。
- `cloud`：DashScope 的 qwen3-tts-flash。音色和本地基座不是一回事，只在本地不可用时兜底。
"""

from __future__ import annotations

import json
import queue
import re
import subprocess
import threading
import time
import unicodedata
from pathlib import Path

ENDPOINT = "/api/v1/services/aigc/multimodal-generation/generation"
PROTO_PREFIX = "__WHALE_TTS__"

_EMOJI = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F000-\U0001F2FF"
    "\uFE0F\u200D"
    "]",
    flags=re.UNICODE,
)
_MARKDOWN = re.compile(r"[*_`~#>|]+")


def clean_for_speech(text: str, max_chars: int = 120) -> str:
    text = _EMOJI.sub("", str(text))
    text = _MARKDOWN.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = unicodedata.normalize("NFKC", text)
    if len(text) > max_chars:
        text = text[:max_chars].rstrip("，。、；：,. ;:")
    return text


class LocalWorker:
    """常驻 Qwen3-TTS 子进程，一行请求一行回话。

    读 stdout 单开一条线程、往 queue 里塞协议行——模型加载日志会把 stdout 弄脏，
    多线程抢着 readline 又会互相偷行，所以只能有一个读者。
    """

    def __init__(self, settings: dict, log=print):
        self.settings = settings
        self.log = log
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._closed = False
        self._counter = 0
        self._queue: "queue.Queue[dict | None]" = queue.Queue()

    def _paths(self) -> tuple[str, str, str, str, str]:
        python = str(Path(self.settings["python"]).expanduser())
        worker = str(Path(self.settings["worker"]).expanduser())
        model = resolve_model_path(self.settings)
        ref_audio = str(Path(self.settings["referenceAudio"]).expanduser())
        ref_text = self.settings.get("referenceText")
        if not ref_text:
            ref_text = Path(self.settings["referenceTextPath"]).expanduser().read_text(encoding="utf-8").strip()
        return python, worker, model, ref_audio, ref_text

    def _reader(self, proc: subprocess.Popen, responses) -> None:
        while True:
            line = proc.stdout.readline()
            if not line:
                responses.put(None)
                return
            if not line.startswith(PROTO_PREFIX):
                continue
            try:
                responses.put(json.loads(line[len(PROTO_PREFIX):].strip()))
            except json.JSONDecodeError:
                continue

    def _ensure(self) -> subprocess.Popen:
        if self._proc is not None and self._proc.poll() is None:
            return self._proc
        python, worker, model, ref_audio, ref_text = self._paths()
        for label, path in (("python", python), ("worker", worker), ("model", model), ("referenceAudio", ref_audio)):
            if not Path(path).exists():
                raise RuntimeError(f"本地 TTS 缺 {label}: {path}")
        command = [
            python, worker,
            "--model", model,
            "--ref-audio", ref_audio,
            "--ref-text", ref_text,
            "--temperature", str(self.settings.get("temperature", 0.7)),
            "--language", str(self.settings.get("language", "Chinese")),
        ]
        self.log("[tts] 启动本地 Qwen3-TTS 进程（首次加载模型要几秒）")
        with self._state_lock:
            if self._closed:
                raise RuntimeError("本地 TTS 已关闭")
            proc = subprocess.Popen(
                command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, bufsize=1,
            )
            self._proc = proc
        self._queue = queue.Queue()
        threading.Thread(target=self._reader, args=(proc, self._queue), daemon=True, name="whale-tts-reader").start()

        try:
            payload = self._queue.get(timeout=180)
        except queue.Empty:
            proc.kill()
            proc.wait()
            raise RuntimeError("本地 TTS 模型加载超时（>180s）")
        if payload is None:
            proc.kill()
            proc.wait()
            raise RuntimeError("本地 TTS 进程启动就退出了")
        if not payload.get("ready"):
            proc.kill()
            proc.wait()
            raise RuntimeError(f"本地 TTS 没就绪: {payload}")
        self.log(f"[tts] 模型加载完成，用了 {payload.get('load_seconds')} 秒")
        self._proc = proc
        return proc

    def synthesize(self, text: str, out: Path) -> Path:
        with self._lock:
            proc = self._ensure()
            if proc.stdin is None:
                raise RuntimeError("本地 TTS 管道断了")
            self._counter += 1
            request_id = str(self._counter)
            proc.stdin.write(json.dumps({"id": request_id, "text": text, "out": str(out)}, ensure_ascii=False) + "\n")
            proc.stdin.flush()
            deadline = time.time() + 240
            while True:
                remaining = deadline - time.time()
                if remaining <= 0:
                    raise RuntimeError("本地 TTS 合成超时")
                try:
                    response = self._queue.get(timeout=remaining)
                except queue.Empty:
                    raise RuntimeError("本地 TTS 合成超时")
                if response is None:
                    self._proc = None
                    raise RuntimeError("本地 TTS 进程退出了")
                if response.get("id") != request_id:
                    continue
                if not response.get("ok"):
                    raise RuntimeError(str(response.get("error", "合成失败")))
                return Path(response["path"])

    def stop(self) -> None:
        with self._state_lock:
            self._closed = True
            proc = self._proc
            self._proc = None
        if proc is not None and proc.poll() is None:
            proc.terminate()
            proc.wait()



def resolve_model_path(settings: dict) -> str:
    """使用明确配置的固定路径，不自动选择其他快照。"""
    if not settings.get("model"):
        raise ValueError("请配置 tts.local.model 并链接模型目录")
    return str(Path(settings["model"]).expanduser())


class Speaker:
    """串行播放：新的一句进来就把上一句掐掉，不叠音。"""

    def __init__(self, config: dict, api_key: str, cache_dir: Path, log=print):
        self.tts = config.get("tts", {})
        self.api_key = api_key
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.log = log
        self.engine = str(self.tts.get("engine", "local"))
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._local: LocalWorker | None = None
        self._condition = threading.Condition()
        self._pending = None
        self._generation = 0
        self._closed = False
        self._working = False
        self._thread = threading.Thread(target=self._consume, daemon=True, name="whale-tts")
        self._thread.start()

    @property
    def enabled(self) -> bool:
        return bool(self.tts.get("enabled", True)) and (self.engine == "local" or bool(self.api_key))

    def speak_async(self, text: str, on_done=None) -> None:
        if not self.enabled:
            if on_done:
                on_done()
            return
        with self._condition:
            if self._closed:
                return
            self._generation += 1
            self._pending = (text, on_done, self._generation)
            self._stop_playback()
            self._condition.notify_all()

    def _stop_playback(self):
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()

    def stop(self) -> None:
        with self._condition:
            self._generation += 1
            self._pending = None
            self._stop_playback()
            self._condition.notify_all()

    def wait_idle(self):
        with self._condition:
            self._condition.wait_for(lambda: not self._working and self._pending is None)

    def shutdown(self) -> None:
        with self._condition:
            self._closed = True
            self._generation += 1
            self._pending = None
            self._stop_playback()
            if self._local is not None:
                self._local.stop()
            self._condition.notify_all()
        self._thread.join()
        if self._local is not None:
            self._local.stop()

    def _consume(self):
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._closed or self._pending is not None)
                if self._closed:
                    return
                text, on_done, generation = self._pending
                self._pending = None
                self._working = True
            try:
                phrase = clean_for_speech(text, int(self.tts.get("maxChars", 120)))
                if phrase:
                    path = self._synth(phrase)
                    with self._condition:
                        if path is not None and generation == self._generation and not self._closed:
                            self._start_playback(path)
                            proc = self._proc
                        else:
                            proc = None
                    if proc is not None:
                        result = proc.wait()
                        with self._condition:
                            if self._proc is proc:
                                self._proc = None
                            cancelled = generation != self._generation or self._closed
                        if not cancelled:
                            if result != 0:
                                raise RuntimeError(f"音频播放失败，afplay 退出码 {result}")
                            self.log("[tts] 播放完成 (afplay exit=0)")
                    if path is not None:
                        for old in sorted(self.cache_dir.glob("say-*.wav"), key=lambda p: p.stat().st_mtime)[:-20]:
                            old.unlink(missing_ok=True)
            except Exception as error:
                self.log(f"[tts] 失败: {error}")
            finally:
                with self._condition:
                    self._working = False
                    self._condition.notify_all()
                if on_done:
                    try:
                        on_done()
                    except Exception as error:
                        self.log(f"[tts] 回调失败: {error}")

    def _synth(self, phrase: str) -> Path | None:
        target = self.cache_dir / f"say-{int(__import__('time').time() * 1000)}.wav"
        if self.engine == "local":
            try:
                with self._condition:
                    if self._closed:
                        return None
                    if self._local is None:
                        self._local = LocalWorker(self.tts.get("local", {}), log=self.log)
                return self._local.synthesize(phrase, target)
            except Exception as error:
                self.log(f"[tts] 本地合成失败: {error}")
                if self._closed or not self.tts.get("fallbackCloud", False):
                    return None
                if not self.api_key:
                    return None
                self.log("[tts] 退回 DashScope 云端音色")
        return self._synth_cloud(phrase, target)

    def synthesize(self, phrase: str) -> Path:
        """同步合成（自检用），不播放。"""
        path = self._synth(phrase)
        if path is None:
            raise RuntimeError("合成失败")
        return path

    # ---------- 云端兜底 ----------

    def _synth_cloud(self, phrase: str, target: Path) -> Path | None:
        import requests

        url = str(self.tts.get("baseURL", "https://dashscope.aliyuncs.com")).rstrip("/") + ENDPOINT
        payload = {
            "model": self.tts.get("model", "qwen3-tts-flash"),
            "input": {"text": phrase, "voice": self.tts.get("voice", "Cherry")},
        }
        response = requests.post(
            url,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=30,
        )
        data = response.json()
        if response.status_code != 200 or "output" not in data:
            raise RuntimeError(str(data)[:300])
        audio_url = (data.get("output") or {}).get("audio", {}).get("url")
        if not audio_url:
            raise RuntimeError(f"没拿到 audio.url: {str(data)[:200]}")
        with requests.get(audio_url, timeout=30, stream=True) as audio:
            audio.raise_for_status()
            target.write_bytes(audio.content)
        return target

    def _start_playback(self, path: Path) -> None:
        volume = float(self.tts.get("volume", 1.0))
        args = ["afplay"]
        if 0 < volume < 1:
            args += ["-v", f"{volume:.2f}"]
        args.append(str(path))
        self._proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.log("[tts] 开始播放")
