"""Convert a bounded sticker image to a single model-ready PNG."""

from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps


FORMATS = ("PNG", "GIF", "WEBP", "JPEG")
MAX_PIXELS = 1_048_576
MAX_DECODED_PIXELS = 32_000_000
MAX_FRAMES = 160


@dataclass(frozen=True)
class Visual:
    png: bytes
    sample_count: int
    limited: bool
    preview: bool


def render(blob: bytes, *, preview: bool = False) -> Visual:
    with Image.open(BytesIO(blob), formats=FORMATS) as sticker:
        area = sticker.width * sticker.height
        if not 0 < area <= MAX_PIXELS:
            raise ValueError("sticker dimensions exceed limit")
        frame_limit = min(MAX_FRAMES, MAX_DECODED_PIXELS // area)
        # Retain bounded small thumbnails while decoding one frame at a time.
        frames = []
        durations = []
        limited = False
        for index in range(frame_limit):
            try:
                sticker.seek(index)
            except EOFError:
                break
            frame = sticker.convert("RGBA")
            if len(frames) == 0 and not getattr(sticker, "is_animated", False):
                return Visual(as_png(fit(frame, 768)), 1, False, preview)
            frames.append(fit(frame, 384))
            duration = sticker.info.get("duration", 100)
            durations.append(max(20, min(1000, duration)) if isinstance(duration, int) else 100)
            if preview:
                return Visual(as_png(frames[0]), 1, True, True)
        if len(frames) == frame_limit:
            try:
                sticker.seek(frame_limit)
            except EOFError:
                pass
            else:
                limited = True

    if len(frames) == 1:
        return Visual(as_png(frames[0]), 1, limited, preview)
    selected = [frames[index] for index in sample_indices(durations)]
    width, height = selected[0].size
    canvas = Image.new("RGBA", ((width + 3) * 2 - 3, (height + 3) * 2 - 3), (244, 244, 244))
    for i, frame in enumerate(selected):
        canvas.alpha_composite(frame, ((i % 2) * (width + 3), (i // 2) * (height + 3)))
    return Visual(as_png(canvas), len(selected), limited, preview)


def fit(frame: Image.Image, edge: int) -> Image.Image:
    return ImageOps.contain(frame, (edge, edge), Image.Resampling.LANCZOS)


def as_png(frame: Image.Image) -> bytes:
    result = BytesIO()
    frame.save(result, "PNG")
    return result.getvalue()


def sample_indices(durations: list[int]) -> list[int]:
    if len(durations) <= 4:
        return list(range(len(durations)))
    total = sum(durations)
    start = 0
    chosen = [0]
    for index, duration in enumerate(durations):
        end = start + duration
        if start <= total / 3 < end or start <= total * 2 / 3 < end:
            chosen.append(index)
        start = end
    return sorted(set((*chosen, len(durations) - 1)))
