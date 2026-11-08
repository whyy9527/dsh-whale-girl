#!/usr/bin/env python3
"""鲸鱼娘看屏 —— 桌面浮窗这边的主程序。

跑起来之后它做四件事，循环往复：
  1. 每隔几秒截一张屏；
  2. 画面变化够大才留下，凑够九张拼成一张九宫格；
  3. 把九宫格发给 DSH 插件（插件再让 DeepSeek 说一句）；
  4. 气泡显示那一句，同时用 Qwen TTS 念出来。

用法：
    python app/main.py                 # 正常跑
    python app/main.py --once          # 只看一眼就退出（调试用）
    python app/main.py --preview "..." # 不截屏，直接显示一句话（调样式用）
    python app/main.py --check         # 自检：权限、插件连通性、TTS、素材
    python app/main.py --demo          # 不截屏，用合成的画面跑通整条链路
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import signal
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import config as config_module  # noqa: E402
from capture import ScreenCaptureDenied, grab, open_permission_settings, permission_hint  # noqa: E402
from frames import FramePicker, KeptFrame, frame_to_jpeg, now_stamp, stitch_grid  # noqa: E402
from overlay import Overlay, activate_app  # noqa: E402
from lifecycle import InstanceLock
from tts import Speaker  # noqa: E402
from chat import Conversation
import autostart

from PyObjCTools import AppHelper  # noqa: E402
from Foundation import NSTimer, NSObject  # noqa: E402


class TerminationDelegate(NSObject):
    def applicationWillTerminate_(self, _notification):
        self.cleanup()


class Brain(threading.Thread):
    """后台线程：截屏 → 挑帧 → 拼图 → 请求 → 交给主线程显示。"""

    def __init__(self, cfg: dict, overlay: Overlay, speaker: Speaker, demo: bool = False, once: bool = False):
        super().__init__(daemon=True, name="whale-brain")
        self.cfg = cfg
        self.overlay = overlay
        self.speaker = speaker
        self.demo = demo
        self.once = once
        self.attempt_done = threading.Event()
        self.picker = FramePicker(
            threshold=float(cfg.get("diffThreshold", 0.06)),
            min_changed_ratio=float(cfg.get("minChangedRatio", 0.18)),
            batch_size=int(cfg.get("batchSize", 9)),
        )
        self.stop_event = threading.Event()
        self.force_look = threading.Event()
        self.paused = not cfg.get("watchEnabled", True)
        self.chat_active = False
        self.pause_generation = 0
        self.last_sent_at = 0.0
        self.permission_warned = False
        self._seen_pause_generation = 0

    # ---------- 主循环 ----------

    def run(self) -> None:
        interval = max(0.5, float(self.cfg.get("sampleIntervalSec", 2.0)))
        while not self.stop_event.is_set():
            try:
                if self._seen_pause_generation != self.pause_generation:
                    self.picker.reset()
                    self._seen_pause_generation = self.pause_generation
                if self.chat_active:
                    self.stop_event.wait(0.3)
                    continue
                if self.paused and not self.force_look.is_set():
                    time.sleep(0.3)
                    continue

                if self.force_look.is_set():
                    self.force_look.clear()
                    try:
                        image = grab() if not self.demo else self._demo_frame()
                        self._send([KeptFrame(image=image, taken_at=time.monotonic(), stamp=now_stamp())], force=True)
                        self.picker.reset()
                    finally:
                        if self.once:
                            # Queue completion after the main-thread comment/speech callback.
                            AppHelper.callAfter(self.attempt_done.set)
                    if self.once:
                        return
                else:
                    batch = self._next_batch()
                    if batch:
                        self._send(batch)
            except ScreenCaptureDenied:
                self._warn_permission()
                time.sleep(5.0)
            except Exception as error:  # 后台线程不能死
                self.log(f"[brain] {error}")
                time.sleep(2.0)
            self.stop_event.wait(interval)

    def _next_batch(self):
        image = grab() if not self.demo else self._demo_frame()
        return self.picker.offer(image)

    def _demo_frame(self):
        """合成一帧：底色渐变 + 一个会走的方块，模拟"界面在变"。"""
        from PIL import Image, ImageDraw

        self._demo_t = getattr(self, "_demo_t", 0) + 1
        image = Image.new("RGB", (1280, 720), (16, 24, 38))
        draw = ImageDraw.Draw(image)
        draw.rectangle([0, 0, 1280, 64], fill=(24, 40, 60))
        for index in range(6):
            y = 120 + index * 80
            draw.rectangle([40, y, 1240, y + 40], fill=(28, 46, 68))
        x = 40 + (self._demo_t * 173) % 700
        draw.rectangle([x, 220, x + 520, 460], fill=(32, 180, 200))
        draw.rectangle([60, 620, 60 + (self._demo_t * 90) % 1100, 660], fill=(220, 120, 60))
        draw.text((60, 24), f"demo frame {self._demo_t}", fill=(200, 220, 235))
        return image

    # ---------- 发送 ----------

    def _payload(self, batch) -> dict:
        mode = str(self.cfg.get("sendMode", "grid"))
        if not batch:
            return {"frames": [], "spanSec": 0}
        use_grid = mode == "grid" and len(batch) == 9
        if not use_grid:
            frames = [
                {"data": base64.b64encode(frame_to_jpeg(item.image)).decode("ascii"), "ts": item.stamp}
                for item in batch
            ]
        else:
            grid = stitch_grid(batch)
            frames = [{"data": base64.b64encode(grid).decode("ascii"), "ts": batch[-1].stamp}]
        span = 0.0
        if len(batch) >= 2:
            span = batch[-1].taken_at - batch[0].taken_at
        return {"frames": frames, "spanSec": span, "grid": use_grid, "cellCount": len(batch)}

    def _send(self, batch, force: bool = False) -> None:
        import requests

        if not force and time.monotonic() - self.last_sent_at < float(self.cfg.get("minSendIntervalSec", 20)):
            return
        if not batch:
            if force:
                AppHelper.callAfter(self.overlay._show_comment, "还没攒到画面变化，等一会儿再说。", "bored")
            return

        generation = self.pause_generation
        payload = self._payload(batch)
        self.last_sent_at = time.monotonic()
        endpoint = str(self.cfg.get("endpoint", "http://127.0.0.1:8791")).rstrip("/")

        try:
            response = requests.post(f"{endpoint}/look", json=payload, timeout=90)
            data = response.json()
        except Exception as error:
            self.log(f"[send] {error}")
            if force:
                AppHelper.callAfter(
                    self.overlay._show_comment,
                    "连不上 DSH 插件，去确认 `dsh web` 开着、插件设置里端口是 8791。",
                    "shock",
                )
            return

        if response.status_code == 409:
            self.log("[send] 上一轮还没看完，跳过")
            return
        if not data.get("ok"):
            message = str(data.get("error", "未知错误"))
            self.log(f"[send] 插件报错: {message}")
            if force:
                AppHelper.callAfter(self.overlay._show_comment, f"翻车了：{message[:60]}", "shock")
            return

        if self.stop_event.is_set() or self.chat_active or generation != self.pause_generation:
            return
        say = str(data.get("say", "")).strip()
        if not say:
            return
        mood = str(data.get("mood", "idle"))
        self.log(f"[say] {say}  ({mood}, {data.get('ms')}ms, {len(batch)} 帧)")
        AppHelper.callAfter(self._deliver_comment, say, mood, generation)

    def _deliver_comment(self, say, mood, generation):
        if self.stop_event.is_set() or self.chat_active or generation != self.pause_generation:
            return
        self.overlay._show_comment(say, mood)
        self.speaker.speak_async(say)

    # ---------- 其它 ----------

    def _warn_permission(self) -> None:
        if self.permission_warned:
            return
        self.permission_warned = True
        AppHelper.callAfter(self.overlay._show_comment, permission_hint(), "shock")
        open_permission_settings()

    def request_look(self) -> None:
        self.force_look.set()

    def toggle_pause(self) -> bool:
        self.paused = not self.paused
        self.pause_generation += 1
        self.speaker.stop()
        return self.paused

    def stop(self) -> None:
        self.stop_event.set()
        self.speaker.stop()

    def log(self, message: str) -> None:
        line = f"{time.strftime('%H:%M:%S')} {message}"
        print(line, flush=True)
        try:
            config_module.LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with config_module.LOG_PATH.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"at": line[:8], "message": message}, ensure_ascii=False) + "\n")
        except OSError:
            pass


PID_PATH = config_module.CONFIG_PATH.parent / "overlay.pid"


def build_overlay(cfg: dict) -> Overlay:
    import art

    expressions = cfg.get("avatar", {}).get("expressionsPath")
    art_paths = art.render_all(config_module.CACHE_DIR, expressions=expressions, mode=cfg.get("avatar", {}).get("mode", "portrait"))
    overlay = Overlay.alloc().initWithArt_({mood: str(path) for mood, path in art_paths.items()})
    avatar = cfg.get("avatar", {})
    overlay._configure(
        size=avatar.get("size", 132),
        x=avatar.get("x", 48),
        y=avatar.get("y", 240),
        bubble_hide=cfg.get("bubbleHideAfterSec", 12),
        always_on_top=avatar.get("alwaysOnTop", True),
        mode=avatar.get("mode", "portrait"),
        fullbody_size=avatar.get("fullbodySize", 360),
    )
    def refresh_art(_timer):
        if overlay._drag._drag_start is not None:
            return
        try:
            overlay._reload_art(art.render_all(config_module.CACHE_DIR, expressions=expressions, mode=avatar.get("mode", "portrait")))
        except OSError as error:
            print(f"[avatar] {error}", flush=True)
    overlay._art_timer = NSTimer.scheduledTimerWithTimeInterval_repeats_block_(1.0, True, refresh_art)
    return overlay


def run_check(cfg: dict) -> int:
    import art

    healthy = True
    print("== 配置 ==")
    print(config_module.CONFIG_PATH)
    print("endpoint:", cfg.get("endpoint"))

    print("\n== 素材 ==")
    paths = art.render_all(config_module.CACHE_DIR, expressions=cfg.get("avatar", {}).get("expressionsPath"), mode=cfg.get("avatar", {}).get("mode", "portrait"))
    print(", ".join(f"{mood}={path.name}" for mood, path in paths.items()))

    print("\n== 插件 ==")
    import requests

    endpoint = str(cfg.get("endpoint", "http://127.0.0.1:8791")).rstrip("/")
    try:
        data = requests.get(f"{endpoint}/health", timeout=5).json()
        healthy = healthy and bool(data.get("ok"))
        print("OK" if data.get("ok") else f"异常: {data}")
        print(json.dumps(data, ensure_ascii=False)[:400])
    except Exception as error:
        healthy = False
        print(f"连不上 {endpoint}: {error}")
        print("→ 先确认 `dsh web` 在跑、插件已装并重启过。")

    print("\n== 截屏权限 ==")
    try:
        image = grab()
        print(f"OK，截到 {image.width}x{image.height}")
    except ScreenCaptureDenied as error:
        healthy = False
        print(f"没有权限: {error}")
        print("→ " + permission_hint())

    print("\n== Qwen TTS ==")
    key = config_module.resolve_api_key(cfg)
    engine = str(cfg.get("tts", {}).get("engine", "local"))
    print("引擎:", engine)
    if engine == "local":
        from tts import resolve_model_path

        settings = cfg.get("tts", {}).get("local", {})
        print("模型:", resolve_model_path(settings))
        print("参考音:", settings.get("referenceAudio"))
    if engine == "cloud" and not key:
        healthy = False
        print("没有 DASHSCOPE_API_KEY")
    else:
        speaker = Speaker(cfg, key, config_module.CACHE_DIR)
        try:
            path = speaker.synthesize("鲸鱼娘自检，一切正常。")
            print(f"OK，{path} ({path.stat().st_size} 字节)")
        except Exception as error:
            healthy = False
            print(f"失败: {error}")
        finally:
            speaker.shutdown()
    return 0 if healthy else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="鲸鱼娘看屏")
    parser.add_argument("--once", action="store_true", help="立刻看一眼然后退出")
    parser.add_argument("--preview", metavar="TEXT", help="只显示一句话，用来调样式")
    parser.add_argument("--check", action="store_true", help="自检")
    parser.add_argument("--demo", action="store_true", help="用合成画面跑整条链路")
    parser.add_argument("--stop", action="store_true", help="停掉已经在跑的浮窗")
    parser.add_argument("--restart", action="store_true", help="停掉旧的再起一个新的")
    args = parser.parse_args()

    cfg = config_module.load()
    if args.check:
        return run_check(cfg)

    instance = InstanceLock(PID_PATH)
    if args.stop or args.restart:
        instance.stop_existing()
        if args.stop:
            instance.close()
            return 0
    elif not instance.acquire():
        print("浮窗已经在跑。要重启用 --restart，要停用 --stop。")
        instance.close()
        return 0
    instance.claim()

    app = activate_app()
    overlay = build_overlay(cfg)
    key = config_module.resolve_api_key(cfg)
    speaker = Speaker(cfg, key, config_module.CACHE_DIR, log=lambda message: print(message, flush=True))

    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: AppHelper.stopEventLoop())
    # Cocoa may idle in C indefinitely; a Python callback lets SIGTERM run.
    signal_timer = NSTimer.scheduledTimerWithTimeInterval_repeats_block_(0.25, True, lambda _: None)
    brain = None
    conversation = None
    cleaned = False

    def cleanup():
        nonlocal cleaned
        if cleaned:
            return
        cleaned = True
        if brain is not None:
            brain.stop()
        signal_timer.invalidate()
        if overlay._art_timer is not None:
            overlay._art_timer.invalidate()
        if conversation is not None:
            conversation.stop()
        overlay._close_controls()
        speaker.shutdown()
        instance.close()
        print("[lifecycle] stopped: audio worker reaped, instance lock released", flush=True)

    # NSApplication.terminate may exit without returning from runEventLoop.
    delegate = TerminationDelegate.alloc().init()
    delegate.cleanup = cleanup
    app.setDelegate_(delegate)

    if args.preview:
        overlay._show_comment(args.preview, "smug")
        AppHelper.runEventLoop()
        cleanup()
        return 0

    brain = Brain(cfg, overlay, speaker, demo=args.demo, once=args.once)

    def update_controls():
        overlay._controls._configure(watch=not brain.paused, voice=speaker.enabled,
            mode=cfg['avatar']['mode'], autostart=autostart.enabled())

    def chat_event(kind, data):
        if cleaned:
            return
        if kind == 'accepted':
            cfg['chat']['sessionId'] = data['sessionId']
            cfg['chat']['pending'] = {key: data[key] for key in ('sessionId', 'requestId')}
            config_module.save(cfg)
        elif kind == 'state':
            status = data['status']
            labels = {'queued': '消息已排队', 'running': 'DSH 正在处理…',
                'approval': '需要确认，请打开 DSH 工作台。', 'complete': '已回复', 'failed': '任务未完成'}
            overlay._controls._set_busy(status not in ('complete', 'failed'), labels[status])
            if status in ('complete', 'failed'):
                text = data.get('text') or data.get('error') or '任务已结束。'
                overlay._controls._append('DSH', text)
                overlay._show_comment(text[:180], 'idle')
                speaker.speak_async(text)
                cfg['chat']['pending'] = None
                config_module.save(cfg)
                brain.chat_active = False
                brain.pause_generation += 1
        elif kind == 'connection':
            overlay._controls._set_busy(True, data['error'])
        elif kind == 'error':
            overlay._controls._append('连接', data['error'])
            overlay._controls._set_busy(False, '连接失败；可在 DSH 工作台确认任务。')
            brain.chat_active = False

    conversation = Conversation(cfg['endpoint'], lambda kind, data: AppHelper.callAfter(chat_event, kind, data))

    def open_workbench():
        def resolve():
            import requests
            try:
                response = requests.post(cfg['endpoint'].rstrip('/') + '/workbench', json={}, timeout=10)
                result = response.json()
                if not result.get('ok'):
                    raise RuntimeError(result.get('error', '无法打开 DSH 工作台'))
            except Exception as error:
                AppHelper.callAfter(overlay._controls._status.setStringValue_, str(error))
        threading.Thread(target=resolve, daemon=True).start()

    def on_menu(action, value):
        if action == 'look':
            brain.request_look()
        elif action == 'send':
            if conversation.send(value, cfg['chat']['sessionId'], cfg['chat']['workspacePath']):
                brain.chat_active = True
                brain.pause_generation += 1
                speaker.stop()
                overlay._controls._append('你', value)
                overlay._controls._set_busy(True, '正在交给 DSH…')
        elif action == 'watch':
            if bool(value) == brain.paused:
                brain.toggle_pause()
            cfg['watchEnabled'] = not brain.paused
            config_module.save(cfg)
        elif action == 'voice':
            cfg['tts']['enabled'] = bool(value)
            speaker.stop()
            config_module.save(cfg)
        elif action == 'mode':
            import art
            avatar = cfg['avatar']
            frame = overlay._window.frame()
            avatar['x'] = int(frame.origin.x)
            avatar['y'] = int(frame.origin.y + overlay._avatar.frame().origin.y)
            avatar['mode'] = value
            overlay._reload_art(art.render_all(config_module.CACHE_DIR, expressions=avatar['expressionsPath'], mode=value))
            overlay._configure(size=avatar['size'], x=avatar['x'], y=avatar['y'],
                bubble_hide=cfg['bubbleHideAfterSec'], always_on_top=avatar['alwaysOnTop'],
                mode=value, fullbody_size=avatar['fullbodySize'])
            overlay._visible = False
            config_module.save(cfg)
        elif action == 'autostart':
            try:
                autostart.configure(value)
            except Exception as error:
                overlay._controls._status.setStringValue_(str(error))
        elif action == 'expressions':
            folder = Path(cfg['avatar']['expressionsPath']).expanduser() / cfg['avatar']['mode']
            folder.mkdir(parents=True, exist_ok=True)
            subprocess.run(['open', str(folder)], check=False)
        elif action == 'workbench':
            open_workbench()
        elif action == 'quit':
            brain.stop()
            AppHelper.stopEventLoop()
        elif action == 'moved' and value:
            cfg['avatar']['x'], cfg['avatar']['y'] = value
            config_module.save(cfg)
        update_controls()

    update_controls()
    if cfg['chat']['pending']:
        brain.chat_active = True
        conversation.resume(cfg['chat']['pending'])
        overlay._controls._set_busy(True, '恢复 DSH 任务状态…')

    overlay._set_callback(on_menu)
    if args.once:
        overlay._show_comment("看一眼先。", "idle")
        brain.request_look()
        def finish_once():
            while not brain.stop_event.wait(0.1):
                if brain.attempt_done.is_set():
                    speaker.wait_idle()
                    AppHelper.callAfter(AppHelper.stopEventLoop)
                    return
        threading.Thread(target=finish_once, daemon=True).start()
    else:
        overlay._show_comment("鲸鱼娘上线了，盯着你呢。", "happy")

    brain.start()
    AppHelper.runEventLoop()
    cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
