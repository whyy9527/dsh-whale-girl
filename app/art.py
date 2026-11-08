"""Local expression overrides and transparent character-over-circle avatars."""

from __future__ import annotations

from pathlib import Path
import hashlib

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

def _circle_mask(size: int) -> Image.Image:
    mask = Image.new("L", (size * 4, size * 4), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size * 4 - 1, size * 4 - 1], fill=255)
    return mask.resize((size, size), Image.LANCZOS)


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
    with Image.open(path) as source:
        image = source.convert("RGBA")
    if image.getchannel("A").getextrema()[0] == 255:
        return _mask_ring(image, mood)
    return render_popout(image, mood)


def render_popout(image: Image.Image, mood: str) -> Image.Image:
    """Transparent character in front of a recessed circle, without clipping hair/tail."""
    size = BASE * 2
    canvas = Image.new("RGBA", (size, size))
    color = RING.get(mood, RING["idle"])
    circle = (size * .14, size * .27, size * .86, size * .99)
    draw = ImageDraw.Draw(canvas)
    draw.ellipse(circle, fill=(8, 28, 46, 245), outline=color + (220,), width=5)
    draw.arc(tuple(v + (8 if i < 2 else -8) for i, v in enumerate(circle)),
             195, 325, fill=(210, 246, 255, 95), width=3)

    character = image.crop(image.getchannel("A").getbbox())
    scale = min(size * .88 / character.width, size * .92 / character.height)
    character = character.resize((round(character.width * scale), round(character.height * scale)), Image.Resampling.LANCZOS)
    x, y = (size - character.width) // 2, int(size * .035)
    silhouette = Image.new("RGBA", canvas.size)
    silhouette.paste(character, (x + 3, y + 16))
    alpha = silhouette.getchannel("A").point(lambda value: int(value * .45))
    shadow = Image.new("RGBA", canvas.size, (0, 4, 14, 0))
    shadow.putalpha(alpha.filter(ImageFilter.GaussianBlur(14)))
    canvas.alpha_composite(shadow)
    canvas.alpha_composite(character, (x, y))
    return canvas.resize((BASE, BASE), Image.Resampling.LANCZOS)


def expression_source(folder: Path | None, mood: str) -> Path | None:
    """Resolve each mood independently: local PNG/WebP, then bundled artwork."""
    for directory in ([folder] if folder else []) + [EXPRESSION_DIR]:
        for suffix in (".png", ".webp"):
            candidate = directory / (mood + suffix)
            if candidate.is_file():
                return candidate
    return None


def render_all(cache_dir: Path, expressions: Path | None = None) -> dict[str, Path]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    folder = Path(expressions).expanduser() if expressions else None
    paths: dict[str, Path] = {}
    for mood in MOODS:
        source = expression_source(folder, mood)
        if source is None:
            raise FileNotFoundError(f"Missing expression: {mood}.png or {mood}.webp")
        stat = source.stat()
        identity = f"popout-v2:{source.resolve()}:{stat.st_mtime_ns}:{stat.st_size}"
        stamp = hashlib.sha256(identity.encode()).hexdigest()[:20]
        target = cache_dir / f"expr-{mood}-{stamp}.png"
        if not target.exists():
            render_expression(source, mood).save(target)
            for stale in cache_dir.glob(f"expr-{mood}-*.png"):
                if stale != target:
                    stale.unlink(missing_ok=True)
        paths[mood] = target
    return paths
