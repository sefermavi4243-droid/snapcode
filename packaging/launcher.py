import sys


def selftest(out_path: str) -> int:
    """Render a snippet, OCR it with the bundled engine and write the result.

    Lets CI and the installer build prove the frozen exe can still reach
    Windows OCR (a windowed exe has no console to print to).
    """
    import io

    from PIL import Image, ImageDraw, ImageFont

    from pluck.config import Settings
    from pluck.pipeline import recognize

    code = "def add(a, b):\n    return a + b"
    font = ImageFont.truetype("consola.ttf", 16)
    image = Image.new("RGB", (360, 80), "white")
    draw = ImageDraw.Draw(image)
    for i, line in enumerate(code.split("\n")):
        draw.text((12, 12 + 24 * i), line, font=font, fill="black")
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    try:
        result = recognize(buffer.getvalue(), Settings(engine="windows")).code
    except Exception as exc:
        result = f"ERROR: {exc}"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(result)
    return 0 if result.strip() == code else 1


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--selftest":
        raise SystemExit(selftest(sys.argv[2]))
    from pluck.app import run_gui

    raise SystemExit(run_gui())
