"""截屏：优先走 Quartz（不落盘、快），不行再退回 `screencapture` 命令行。

macOS 从 10.15 起，谁截屏谁就得在「系统设置 → 隐私与安全性 → 屏幕录制」里被勾上；
没勾的时候 Quartz 返回 None、screencapture 报 "could not create image from display"。
两种情况都抛 ScreenCaptureDenied，让上层弹一句话引导用户去开权限。
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

try:  # pyobjc 没装的话，整个模块只保留 CLI 那条路
    import Quartz  # type: ignore
except Exception:  # pragma: no cover - 取决于机器
    Quartz = None


class ScreenCaptureDenied(RuntimeError):
    """系统没给屏幕录制权限。"""


def _pil_from_cgimage(image) -> Image.Image:
    width = Quartz.CGImageGetWidth(image)
    height = Quartz.CGImageGetHeight(image)
    bytes_per_row = Quartz.CGImageGetBytesPerRow(image)
    provider = Quartz.CGImageGetDataProvider(image)
    data = Quartz.CGDataProviderCopyData(provider)
    buffer = bytes(data)
    # CGImage 给的是 BGRA 或 RGBA，按 4 字节取前 3 个通道；行尾可能有 padding，先切掉。
    expected = bytes_per_row * height
    if len(buffer) < expected:
        raise ScreenCaptureDenied("截屏数据不完整")
    raw = np.frombuffer(buffer, dtype=np.uint8, count=expected).reshape(height, bytes_per_row)
    raw = raw[:, : width * 4].reshape(height, width, 4)
    rgb = raw[:, :, :3][:, :, ::-1]  # BGR -> RGB
    return Image.fromarray(np.ascontiguousarray(rgb), mode="RGB")


def _grab_quartz() -> Image.Image:
    rect = Quartz.CGRectInfinite
    image = Quartz.CGWindowListCreateImage(
        rect,
        Quartz.kCGWindowListOptionOnScreenOnly,
        Quartz.kCGNullWindowID,
        Quartz.kCGWindowImageDefault,
    )
    if image is None:
        raise ScreenCaptureDenied("Quartz 拿不到画面（多半是没开屏幕录制权限）")
    return _pil_from_cgimage(image)


def _grab_cli() -> Image.Image:
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
        path = Path(handle.name)
    try:
        result = subprocess.run(
            ["screencapture", "-x", "-t", "png", str(path)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0 or not path.exists():
            raise ScreenCaptureDenied(
                (result.stderr or "screencapture 失败").strip() or "屏幕录制权限没开"
            )
        return Image.open(path).convert("RGB")
    finally:
        path.unlink(missing_ok=True)


def grab() -> Image.Image:
    """截一张全屏（所有显示器拼起来的那张大图）。"""
    if Quartz is not None:
        try:
            return _grab_quartz()
        except ScreenCaptureDenied:
            pass
        except Exception:
            pass
    return _grab_cli()


def permission_hint() -> str:
    return (
        "没拿到屏幕录制权限。打开「系统设置 → 隐私与安全性 → 屏幕录制」，"
        "把运行这个浮窗的程序（终端 / Python）勾上，然后重开浮窗。"
    )


def open_permission_settings() -> None:
    """直接跳到屏幕录制那一页，省得用户自己翻。"""
    url = "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
    subprocess.run(["open", url], check=False)
