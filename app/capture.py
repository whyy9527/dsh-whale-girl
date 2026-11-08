"""Quartz window composition; exclude the entire companion process before sampling."""

from __future__ import annotations

import os
import subprocess

import numpy as np
from PIL import Image

import Quartz


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


def grab() -> Image.Image:
    """Compose on-screen windows in system order, excluding this process's windows."""
    if not Quartz.CGPreflightScreenCaptureAccess():
        raise ScreenCaptureDenied("屏幕录制权限未开启")
    windows = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID)
    window_ids = [int(window['kCGWindowNumber']) for window in windows
                  if window['kCGWindowOwnerPID'] != os.getpid()]
    image = Quartz.CGWindowListCreateImageFromArray(Quartz.CGRectInfinite, window_ids, Quartz.kCGWindowImageDefault)
    if image is None:
        raise ScreenCaptureDenied("Quartz 没有返回排除桌宠后的画面")
    return _pil_from_cgimage(image)


def permission_hint() -> str:
    return (
        "没拿到屏幕录制权限。打开「系统设置 → 隐私与安全性 → 屏幕录制」，"
        "把运行这个浮窗的程序（终端 / Python）勾上，然后重开浮窗。"
    )


def open_permission_settings() -> None:
    """直接跳到屏幕录制那一页，省得用户自己翻。"""
    url = "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
    subprocess.run(["open", url], check=False)
