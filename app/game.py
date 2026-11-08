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


def changes(before: dict | None, after: dict | None) -> list[str]:
    """Describe differences between submitted public snapshots, not inferred actions."""
    if not after or after.get('error') or after.get('inCombat'):
        return []
    quest = after.get('selectedQuest') or {}
    if not before or before.get('error') or before.get('inCombat'):
        return [f"首次观察：{after.get('zone', '')}；选中任务“{quest.get('title', '')}”({quest.get('id', '未知')})"]
    events = []
    if (before.get('zone'), before.get('subzone')) != (after.get('zone'), after.get('subzone')):
        events.append(f"区域：{before.get('zone', '')}/{before.get('subzone', '')} → {after.get('zone', '')}/{after.get('subzone', '')}")
    if before.get('level') is not None and after.get('level') is not None and before['level'] != after['level']:
        events.append(f"等级：{before['level']} → {after['level']}")
    old = before.get('selectedQuest') or {}
    if old.get('id') != quest.get('id'):
        events.append(f"选中任务：{old.get('title', '')}({old.get('id', '无')}) → {quest.get('title', '')}({quest.get('id', '无')})；仅表示选中项变化，不代表用户已决定目标")
    elif old.get('objectives') != quest.get('objectives'):
        events.append(f"任务“{quest.get('title', '')}”({quest.get('id')})目标：{'；'.join(old.get('objectives') or [])} → {'；'.join(quest.get('objectives') or [])}")
    previous = {q['id']: q.get('complete', False) for q in before.get('quests', [])}
    current = {q['id']: q.get('complete', False) for q in after.get('quests', [])}
    for qid, complete in current.items():
        if qid not in previous:
            events.append(f"任务列表新增：{qid}，{'已完成' if complete else '未完成'}")
        elif previous[qid] != complete:
            events.append(f"任务 {qid}：{'已完成' if previous[qid] else '未完成'} → {'已完成' if complete else '未完成'}")
    # A truncated list cannot prove removal, and removal does not prove turn-in.
    if not after.get('truncated'):
        events.extend(f"任务列表不再显示：{qid}（不能据此断言已交付）" for qid in previous.keys() - current.keys())
    return [event[:1000] for event in events[:12]]


def choice_reply(question: str, choice: str) -> str:
    """A native button click is an explicit answer, anchored to its question."""
    return f'关于你刚才问的“{question}”，我选“{choice}”。请接着这个选择回应。'


def guide_is_obsolete(before: dict | None, after: dict | None) -> bool:
    """Discard only a confirmed client/area change, not ordinary game progress.

    Missing data is not proof that a fixed destination or a short reaction is
    obsolete. Replies describe the observed snapshot, never live distance.
    """
    if not before or not after or before.get('error') or after.get('error'):
        return False
    return any(before.get(key) is not None and after.get(key) is not None
               and before[key] != after[key] for key in ('build', 'mapId', 'zone'))


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
