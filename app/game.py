"""Decode WhaleBridge's visible, calibrated pixel panel before image resizing.

This is a sensor, not a history store. A missing, corrupt or stale panel yields
no current game state. Both conversation paths attach the same wire snapshot.
"""
from __future__ import annotations

import json
import struct
import time
import zlib

import numpy as np
from PIL import Image

COLUMNS, ROWS, PREFIX_CELLS, MAX_BODY = 64, 32, 72, 1400
MARKER = np.array([(255, 0, 255), (0, 0, 0), (255, 0, 255), (0, 255, 0),
                   (255, 0, 255), (0, 0, 0), (0, 255, 255), (255, 255, 0)])


def decode(image: Image.Image, now: float | None = None) -> dict | None:
    pixels = np.asarray(image.convert('RGB'))
    magenta = (pixels[:, :, 0] > 210) & (pixels[:, :, 1] < 45) & (pixels[:, :, 2] > 210)
    corners = magenta.copy()
    corners[:, 1:] &= ~magenta[:, :-1]
    corners[1:, :] &= ~magenta[:-1, :]
    ys, xs = np.where(corners)
    for y, x in zip(ys[:128], xs[:128]):
        width = 0
        while x + width < image.width and magenta[y, x + width] and width <= 16:
            width += 1
        height = 0
        while y + height < image.height and magenta[y + height, x] and height <= 16:
            height += 1
        if not (2 <= width <= 16 and 2 <= height <= 16):
            continue
        if x + COLUMNS * width > image.width or y + ROWS * height > image.height:
            continue
        cols = x + np.arange(COLUMNS) * width + width // 2
        rows = y + np.arange(ROWS) * height + height // 2
        cells = pixels[rows[:, None], cols].reshape(-1, 3).astype(np.int16)
        if np.max(np.abs(cells[:8] - MARKER)) > 110:
            continue
        calibration = cells[8:PREFIX_CELLS].astype(np.int32)
        if np.any(np.ptp(calibration, axis=0) < 100):
            continue
        distances = np.sum((cells[PREFIX_CELLS:, None, :].astype(np.int32) - calibration[None, :, :]) ** 2, axis=2)
        symbols = np.argmin(distances, axis=1)
        bits = ((symbols[:, None] >> np.arange(5, -1, -1)) & 1).astype(np.uint8).reshape(-1)
        raw = np.packbits(bits).tobytes()
        if raw[:4] != b'WGB1':
            continue
        length, sequence, checksum = struct.unpack('>HII', raw[4:14])
        if length > MAX_BODY or length + 14 > len(raw):
            continue
        body = raw[14:14 + length]
        if zlib.adler32(body) != checksum:
            continue
        try:
            state = json.loads(body)
            if not isinstance(state, dict) or state.get('version') != 1:
                continue
            sampled = state.get('sampledAt')
            if not isinstance(sampled, (int, float)) or not -2 <= (time.time() if now is None else now) - sampled <= 5:
                continue
        except (ValueError, UnicodeError):
            continue
        return {**state, 'sequence': sequence}
    return None


def current() -> dict | None:
    """One fresh read on an explicit text request; never reuse an old position."""
    from capture import grab, ScreenCaptureDenied
    try:
        return decode(grab())
    except ScreenCaptureDenied:
        return None
