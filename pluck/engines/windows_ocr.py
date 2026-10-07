"""Offline OCR through the Windows.Media.Ocr engine built into Windows 10/11."""

from __future__ import annotations

import asyncio
import io

from PIL import Image, ImageChops

from ..postprocess import OcrLine, OcrWord
from ..i18n import t


class PixelProbe:
    """Answers "is there ink here?" questions for the post-processor."""

    def __init__(self, image: Image.Image) -> None:
        self.gray = image.convert("L")
        self._px = self.gray.load()

    def has_underscore(self, x0: float, x1: float, y0: float, y1: float) -> bool:
        w, h = self.gray.size
        xs = range(max(0, int(x0)), min(w, int(x1) + 1))
        if len(xs) < 2:
            return False
        for y in range(max(0, int(y0)), min(h, int(y1) + 1)):
            dark = sum(1 for x in xs if self._px[x, y] < 128)
            if dark >= 0.65 * len(xs):
                return True
        return False


class WindowsOcrUnavailable(RuntimeError):
    pass


# Small text OCRs badly; upscale so glyphs are at least ~30px tall.
_MIN_UPSCALE_EDGE = 2600
_PADDING = 40
# Contrast boost for faint (dim, coloured) text after background removal.
_INK_GAIN = 1.6


def _load_winrt():
    try:
        from winrt.windows.globalization import Language
        from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
        from winrt.windows.media.ocr import OcrEngine
        from winrt.windows.storage.streams import DataWriter
    except ImportError as exc:
        raise WindowsOcrUnavailable(
            "Windows OCR paketleri eksik: pip install winrt-Windows.Media.Ocr "
            "winrt-Windows.Graphics.Imaging winrt-Windows.Storage.Streams winrt-Windows.Globalization"
        ) from exc
    return Language, BitmapPixelFormat, SoftwareBitmap, OcrEngine, DataWriter


def available_languages() -> list[str]:
    _, _, _, OcrEngine, _ = _load_winrt()
    return [lang.language_tag for lang in OcrEngine.available_recognizer_languages]


def _normalize(image: Image.Image) -> Image.Image:
    """Return RGBA with dark text on a white background, whatever the colours.

    Brightness alone loses syntax highlighting: a purple bracket or a dim
    green comment on a dark theme ends up as mid-grey and OCR drops it, and a
    diff's red and green line backgrounds break any single threshold. So
    measure ink as the colour distance from the background of its own pixel
    row (the most common colour there), with a fixed contrast boost.
    """
    if image.mode in ("RGBA", "LA", "P"):
        image = image.convert("RGBA")
        flat = Image.new("RGB", image.size, (255, 255, 255))
        flat.paste(image, mask=image.getchannel("A"))
        image = flat
    rgb = image.convert("RGB")
    width, height = rgb.size
    rows = []
    for y in range(height):
        colors = rgb.crop((0, y, width, y + 1)).getcolors(width)
        rows.append(max(colors)[1])
    strip = Image.new("RGB", (1, height))
    strip.putdata(rows)
    background = strip.resize((width, height), Image.Resampling.NEAREST)

    # Perceptual weights keep thin anti-aliased edges thin; the plain
    # per-channel maximum makes glyphs bolder and OCR confuses "." with "-".
    r, g, b = ImageChops.difference(rgb, background).split()
    ink = ImageChops.add(
        ImageChops.add(r.point(lambda v: v * 0.3), g.point(lambda v: v * 0.45)), b.point(lambda v: v * 0.25)
    )
    # Boost only as far as needed for the strongest ink (ignoring the top
    # 0.2% of outliers) to turn black: high-contrast text stays as drawn,
    # dim text gets up to _INK_GAIN.
    histogram = ink.histogram()
    budget = sum(histogram) * 0.002
    peak = 255
    while peak > 1 and budget > 0:
        budget -= histogram[peak]
        peak -= 1
    gain = min(_INK_GAIN, 255 / max(peak, 1))
    return ink.point(lambda v: 255 - min(255, round(v * gain))).convert("RGBA")


def _prepare(image: Image.Image, upscale: bool) -> tuple[Image.Image, float, int]:
    scale = 1.0
    longest = max(image.size)
    if upscale and longest < _MIN_UPSCALE_EDGE:
        scale = min(3.0, _MIN_UPSCALE_EDGE / longest)
        image = image.resize(
            (round(image.width * scale), round(image.height * scale)), Image.Resampling.LANCZOS
        )
    # A margin keeps glyphs at the edge of a tight crop from being dropped.
    pad = round(_PADDING * scale)
    padded = Image.new("RGBA", (image.width + 2 * pad, image.height + 2 * pad), (255, 255, 255, 255))
    padded.paste(image, (pad, pad))
    return padded, scale, pad


async def _recognize(
    source: Image.Image, language_tag: str, upscale: bool
) -> tuple[list[OcrLine], PixelProbe]:
    Language, BitmapPixelFormat, SoftwareBitmap, OcrEngine, DataWriter = _load_winrt()

    engine = None
    if language_tag:
        lang = Language(language_tag)
        if OcrEngine.is_language_supported(lang):
            engine = OcrEngine.try_create_from_language(lang)
    if engine is None:
        engine = OcrEngine.try_create_from_user_profile_languages()
    if engine is None:
        raise WindowsOcrUnavailable(t("Bu sistemde Windows OCR dil paketi yüklü değil."))

    original = _normalize(source)
    image, scale, pad = _prepare(original, upscale)
    factor = 1.0
    limit = OcrEngine.max_image_dimension
    if max(image.size) > limit:
        factor = limit / max(image.size)
        image = image.resize((int(image.width * factor), int(image.height * factor)))

    def to_source(v: float) -> float:
        # OCR pixels = (source * scale + pad) * factor
        return (v / factor - pad) / scale

    writer = DataWriter()
    writer.write_bytes(image.tobytes("raw", "BGRA"))
    bitmap = SoftwareBitmap.create_copy_from_buffer(
        writer.detach_buffer(), BitmapPixelFormat.BGRA8, image.width, image.height
    )
    result = await engine.recognize_async(bitmap)

    lines = []
    for line in result.lines:
        words = [
            OcrWord(
                text=w.text,
                x=to_source(w.bounding_rect.x),
                y=to_source(w.bounding_rect.y),
                width=w.bounding_rect.width / factor / scale,
                height=w.bounding_rect.height / factor / scale,
            )
            for w in line.words
        ]
        if words:
            lines.append(OcrLine(words))
    return lines, PixelProbe(original)


def recognize(png: bytes, language_tag: str = "en-US") -> tuple[list[OcrLine], PixelProbe]:
    """Return OCR rows in source-image pixels plus a probe into those pixels."""
    return asyncio.run(_recognize(Image.open(io.BytesIO(png)), language_tag, upscale=True))
