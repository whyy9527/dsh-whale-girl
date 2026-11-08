"""Keep substantial screen changes; send full batches only, without timed commentary."""

from __future__ import annotations

import io
import time
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
from PIL import Image, ImageDraw, ImageFont

FINGERPRINT_SIZE = (64, 36)
CELL_SIZE = (640, 360)
GRID_GAP = 6
GRID_BG = (9, 16, 30)


def fingerprint(image: Image.Image) -> np.ndarray:
    small = image.convert("L").resize(FINGERPRINT_SIZE, Image.BILINEAR)
    return np.asarray(small, dtype=np.float32)


def difference(a: np.ndarray, b: np.ndarray) -> float:
    """0..1 的平均像素差。"""
    if a.shape != b.shape:
        return 1.0
    return float(np.abs(a - b).mean() / 255.0)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _to_cell(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """等比塞进格子，空白处填深色，不裁掉内容。"""
    target_w, target_h = size
    ratio = min(target_w / image.width, target_h / image.height)
    resized = image.resize((max(1, int(image.width * ratio)), max(1, int(image.height * ratio))), Image.LANCZOS)
    cell = Image.new("RGB", size, GRID_BG)
    cell.paste(resized, ((target_w - resized.width) // 2, (target_h - resized.height) // 2))
    return cell


@dataclass
class KeptFrame:
    image: Image.Image
    taken_at: float
    stamp: str


def stitch_grid(frames: list[KeptFrame]) -> bytes:
    """完整批次按时间排列为 2×2 或 3×3；不创建空白格。"""
    if len(frames) not in (4, 9):
        raise ValueError('拼图需要完整的 4 张或 9 张画面')
    cols = rows = 2 if len(frames) == 4 else 3
    cell_w, cell_h = CELL_SIZE
    width = cols * cell_w + (cols + 1) * GRID_GAP
    height = rows * cell_h + (rows + 1) * GRID_GAP
    canvas = Image.new("RGB", (width, height), GRID_BG)
    draw = ImageDraw.Draw(canvas)
    label_font = _font(26)
    hint_font = _font(18)

    for index, frame in enumerate(frames):
        row, col = divmod(index, cols)
        x = GRID_GAP + col * (cell_w + GRID_GAP)
        y = GRID_GAP + row * (cell_h + GRID_GAP)
        canvas.paste(_to_cell(frame.image, CELL_SIZE), (x, y))

        badge = f"{index + 1}"
        draw.rectangle([x, y, x + 46, y + 38], fill=(16, 185, 210))
        draw.text((x + 13, y + 5), badge, font=label_font, fill=(6, 20, 30))
        stamp = frame.stamp
        box = draw.textbbox((0, 0), stamp, font=hint_font)
        draw.rectangle([x + cell_w - (box[2] - box[0]) - 18, y, x + cell_w, y + 30], fill=(0, 0, 0))
        draw.text((x + cell_w - (box[2] - box[0]) - 9, y + 5), stamp, font=hint_font, fill=(210, 230, 240))

    # 顺序导引：左上角放一句人话，模型看得懂，人也看得懂
    draw.text(
        (GRID_GAP + 6, height - GRID_GAP - 4),
        f"1 -> {len(frames)}  oldest to newest",
        font=hint_font,
        fill=(120, 150, 170),
        anchor="lb",
    )

    buffer = io.BytesIO()
    canvas.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def frame_to_jpeg(image: Image.Image, max_width: int = 960, quality: int = 82) -> bytes:
    if image.width > max_width:
        ratio = max_width / image.width
        image = image.resize((max_width, max(1, int(image.height * ratio))), Image.LANCZOS)
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=quality, optimize=True)
    return buffer.getvalue()


def now_stamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


@dataclass
class FramePicker:
    """状态机：喂它一张图，它决定留不留；凑够了就吐出一批。"""

    threshold: float = 0.06
    min_changed_ratio: float = 0.18
    batch_size: int = 4
    kept: list[KeptFrame] = field(default_factory=list)
    baseline: np.ndarray | None = None

    def reset(self) -> None:
        self.kept.clear()
        self.baseline = None

    def offer(self, image: Image.Image) -> list[KeptFrame] | None:
        """喂一帧。攒够了一批就返回它，否则返回 None。"""
        fp = fingerprint(image)
        if self.baseline is None:
            self.baseline = fp
            return None
        changed = difference(fp, self.baseline)
        changed_ratio = float(np.mean(np.abs(fp - self.baseline) >= 24))
        if changed < self.threshold or changed_ratio < self.min_changed_ratio:
            return None
        self.kept.append(KeptFrame(image=image, taken_at=time.monotonic(), stamp=now_stamp()))
        self.baseline = fp
        if len(self.kept) >= self.batch_size:
            return self._take()
        return None

    def _take(self) -> list[KeptFrame] | None:
        if not self.kept:
            return None
        batch = list(self.kept)
        self.kept.clear()
        return batch

    @property
    def span_sec(self) -> float:
        if len(self.kept) < 2:
            return 0.0
        return self.kept[-1].taken_at - self.kept[0].taken_at
