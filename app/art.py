"""Render the bundled expression series into circular avatars.

An optional local portrait can provide a six-ring fallback when the expression
series is absent. Personal portraits are never distributed with the project.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

BASE = 512
MOODS = ("idle", "smug", "shock", "happy", "bored", "angry")

# 情绪 → 外圈颜色（角色不出戏，只换光环）
RING = {
    "idle": (150, 225, 240),
    "smug": (255, 205, 120),
    "shock": (255, 130, 150),
    "happy": (140, 235, 170),
    "bored": (150, 160, 175),
    "angry": (255, 105, 105),
}

DEFAULT_PORTRAIT = Path(__file__).resolve().parent.parent / "assets" / "character" / "portrait.png"


def _crop_head(image: Image.Image) -> Image.Image:
    """把立绘裁成头部正方形：上缘留一点发型，下缘到肩。"""
    width, height = image.size
    left = int(width * 0.14)
    right = int(width * 0.87)
    top = int(height * 0.02)
    bottom = int(height * 0.55)
    box_w, box_h = right - left, bottom - top
    side = min(box_w, box_h)
    cx = (left + right) // 2
    cy = (top + bottom) // 2
    left = max(0, min(width - side, cx - side // 2))
    top = max(0, min(height - side, cy - side // 2))
    return image.crop((left, top, left + side, top + side))


def _circle_mask(size: int) -> Image.Image:
    mask = Image.new("L", (size * 4, size * 4), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size * 4 - 1, size * 4 - 1], fill=255)
    return mask.resize((size, size), Image.LANCZOS)


def render_portrait(portrait: Path, mood: str) -> Image.Image:
    """裁脸 → 圆形 → 加情绪光环，输出 512x512。"""
    canvas_size = BASE * 2  # 超采样
    source = Image.open(portrait).convert("RGB")
    head = _crop_head(source).resize((canvas_size, canvas_size), Image.LANCZOS)

    canvas = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    mask = _circle_mask(canvas_size)

    # 圆形底下垫一层深海底，边缘过渡才不脏
    backdrop = Image.new("RGBA", (canvas_size, canvas_size), (8, 26, 42, 255))
    canvas.paste(backdrop, (0, 0), mask)
    canvas.paste(head, (0, 0), mask)

    # 顶部一点冷光，让脸从背景里浮出来
    glow = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse(
        [canvas_size * 0.1, -canvas_size * 0.25, canvas_size * 0.9, canvas_size * 0.45],
        fill=(120, 200, 235, 60),
    )
    glow = glow.filter(ImageFilter.GaussianBlur(canvas_size // 14))
    glow.putalpha(Image.composite(glow.getchannel("A"), Image.new("L", glow.size, 0), mask))
    canvas.alpha_composite(glow)

    # 情绪光环 + 一圈内描边
    ring = ImageDraw.Draw(canvas)
    color = RING.get(mood, RING["idle"])
    width = max(2, canvas_size // 128)
    ring.ellipse(
        [width, width, canvas_size - width - 1, canvas_size - width - 1],
        outline=color + (235,),
        width=width,
    )
    ring.ellipse(
        [width * 3, width * 3, canvas_size - width * 3 - 1, canvas_size - width * 3 - 1],
        outline=(255, 255, 255, 45),
        width=max(1, width // 2),
    )

    return canvas.resize((BASE, BASE), Image.LANCZOS)


EXPRESSION_DIR = Path(__file__).resolve().parent.parent / "assets" / "expressions"


def _mask_ring(image: Image.Image, mood: str) -> Image.Image:
    """把任意方形图套成圆形头像 + 情绪光环。"""
    canvas_size = BASE * 2
    square = _center_square(image).resize((canvas_size, canvas_size), Image.LANCZOS).convert("RGBA")
    canvas = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    mask = _circle_mask(canvas_size)
    canvas.paste(Image.new("RGBA", (canvas_size, canvas_size), (8, 26, 42, 255)), (0, 0), mask)
    canvas.alpha_composite(square)
    canvas.putalpha(mask)

    ring = ImageDraw.Draw(canvas)
    color = RING.get(mood, RING["idle"])
    width = max(2, canvas_size // 128)
    ring.ellipse([width, width, canvas_size - width - 1, canvas_size - width - 1], outline=color + (235,), width=width)
    return canvas.resize((BASE, BASE), Image.LANCZOS)


def _center_square(image: Image.Image) -> Image.Image:
    side = min(image.size)
    left = (image.width - side) // 2
    top = (image.height - side) // 2
    return image.crop((left, top, left + side, top + side))


def render_expression(path: Path, mood: str) -> Image.Image:
    return _mask_ring(Image.open(path).convert("RGBA"), mood)


def render_all(cache_dir: Path, portrait: Path | None = None, expressions: Path | None = None) -> dict[str, Path]:
    """优先用生成好的表情图；没有就退回"一张立绘 + 情绪光环"。"""
    cache_dir.mkdir(parents=True, exist_ok=True)
    folder = Path(expressions).expanduser() if expressions else EXPRESSION_DIR
    paths: dict[str, Path] = {}
    if folder.is_dir() and all((folder / f"{mood}.webp").exists() for mood in MOODS):
        for mood in MOODS:
            source = folder / f"{mood}.webp"
            stamp = int(source.stat().st_mtime)
            target = cache_dir / f"expr-{mood}-{stamp}.png"
            if not target.exists():
                render_expression(source, mood).save(target)
                for stale in cache_dir.glob(f"expr-{mood}-*.png"):
                    if stale != target:
                        stale.unlink(missing_ok=True)
            paths[mood] = target
        return paths

    source = Path(portrait).expanduser() if portrait else DEFAULT_PORTRAIT
    if not source.exists():
        return drawn_fallback(cache_dir)

    stamp = int(source.stat().st_mtime)
    for mood in MOODS:
        path = cache_dir / f"dsh-{mood}-{stamp}.png"
        if not path.exists():
            render_portrait(source, mood).save(path)
            for stale in cache_dir.glob(f"dsh-{mood}-*.png"):
                if stale != path:
                    stale.unlink(missing_ok=True)
        paths[mood] = path
    return paths


# --------------------------------------------------------------------------
# 兜底：找不到立绘时画一个占位圆，不伪造角色形象
# --------------------------------------------------------------------------


def drawn_fallback(cache_dir: Path) -> dict[str, Path]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for mood in MOODS:
        path = cache_dir / f"placeholder-{mood}.png"
        if not path.exists():
            _placeholder(mood).save(path)
        paths[mood] = path
    return paths


def _placeholder(mood: str) -> Image.Image:
    size = 512
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size - 1, size - 1], fill=255)
    canvas.paste(Image.new("RGBA", (size, size), (10, 32, 52, 255)), (0, 0), mask)

    draw = ImageDraw.Draw(canvas)
    draw.text((size / 2, size / 2 - 10), "DeepSeek", anchor="mm", fill=(200, 235, 250))
    draw.text((size / 2, size / 2 + 34), "立绘未找到", anchor="mm", fill=(120, 170, 195))
    color = RING.get(mood, RING["idle"])
    draw.ellipse([3, 3, size - 4, size - 4], outline=color + (210,), width=5)
    return canvas


def preview_sheet(path: Path, portrait: Path | None = None) -> None:
    source = Path(portrait).expanduser() if portrait else DEFAULT_PORTRAIT
    images = [render_portrait(source, mood) if source.exists() else _placeholder(mood) for mood in MOODS]
    sheet = Image.new("RGB", (BASE * 3, BASE * 2), (10, 20, 30))
    for index, image in enumerate(images):
        row, col = divmod(index, 3)
        sheet.paste(image, (col * BASE, row * BASE), image)
    sheet.save(path)
