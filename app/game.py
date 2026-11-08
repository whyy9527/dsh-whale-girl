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

COLUMNS, ROWS, PREFIX_CELLS, MAX_BODY = 128, 16, 72, 1400
MARKER = np.array([(255, 0, 255), (0, 0, 0), (255, 0, 255), (0, 255, 0),
                   (255, 0, 255), (0, 0, 0), (0, 255, 255), (255, 255, 0)])


def same_task(before: dict | None, after: dict | None) -> bool:
    """Recheck the live task before speaking a potentially slow guide result.

    Walking within the same map does not invalidate fixed NPC destinations.
    Player distance/direction must not be presented as a real-time fact.
    """
    def signature(state):
        if not state or state.get('inCombat') or state.get('error'):
            return None
        quest = state.get('selectedQuest') or {}
        return (state.get('build'), state.get('mapId'), state.get('zone'), quest.get('id'),
                quest.get('complete'), tuple(quest.get('objectives') or []),
                tuple(sorted((q['id'], q.get('complete', False)) for q in state.get('quests', []))))
    initial, current = signature(before), signature(after)
    return initial is not None and initial == current


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
        # WoW/macOS can rasterize 2 UI pixels as e.g. 3.75 display pixels.
        # Marker columns 0, 2, 4 determine the pitch; rounding a single cell
        # accumulates error across the entire strip.
        row = magenta[y, x:min(image.width, x + width * 7)]
        starts = np.flatnonzero(row & ~np.r_[False, row[:-1]])
        if len(starts) < 3:
            continue
        pitch = starts[2] / 4
        if not 1.5 <= pitch <= 16 or abs(height - pitch) > 1:
            continue
        if x + COLUMNS * pitch > image.width + 1 or y + ROWS * pitch > image.height + 1:
            continue
        cols = np.floor(x + (np.arange(COLUMNS) + .5) * pitch).astype(int)
        rows = np.floor(y + (np.arange(ROWS) + .5) * pitch).astype(int)
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


def view() -> dict | None:
    """Foreground provenance for image-only game help, without a visible data bar."""
    from AppKit import NSWorkspace
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    if app and app.bundleIdentifier() == 'com.blizzard.worldofwarcraft' and '/_forever_/' in str(app.bundleURL().path()):
        return {'client': 'wow-forever', 'sampledAt': time.time()}
    return None
