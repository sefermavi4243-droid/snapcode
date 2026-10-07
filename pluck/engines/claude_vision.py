"""High-accuracy transcription with Claude's vision model.

Unlike classic OCR, the model reads code the way a developer does: it keeps
exact indentation, distinguishes ``l``/``1``/``I`` and ``O``/``0`` from
context, and ignores editor chrome such as tabs, gutters and minimaps.
"""

from __future__ import annotations

import base64
import io
import json

from PIL import Image

from ..i18n import t


class ClaudeError(RuntimeError):
    pass


SYSTEM_PROMPT = """You transcribe source code from screenshots.

Return the code exactly as it appears: same characters, same indentation \
(spaces vs tabs as best you can tell), same blank lines. Do not fix bugs, \
reformat, translate, or complete truncated code. Leave out anything that is \
not part of the code itself: editor line numbers, tab titles, gutters, \
minimaps, cursor artefacts, shell prompts such as "$ " or ">>> " in front of \
commands. If the screenshot shows several separate snippets, join them with a \
blank line. If there is no code, return an empty string for "code".

"language" is the lowercase language name (python, javascript, typescript, \
java, csharp, cpp, c, go, rust, php, ruby, kotlin, swift, html, css, sql, \
bash, powershell, json, yaml, dockerfile, or text). "notes" is one short \
sentence about anything you could not read, or an empty string."""

_SCHEMA = {
    "type": "object",
    "properties": {
        "language": {"type": "string"},
        "code": {"type": "string"},
        "notes": {"type": "string"},
    },
    "required": ["language", "code", "notes"],
    "additionalProperties": False,
}

# The API caps a base64 image at 5 MB; leave headroom.
_MAX_IMAGE_BYTES = 4_500_000


def _shrink(png: bytes) -> tuple[bytes, str]:
    if len(png) <= _MAX_IMAGE_BYTES:
        return png, "image/png"
    image = Image.open(io.BytesIO(png)).convert("RGB")
    image.thumbnail((2400, 2400), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    image.save(out, "JPEG", quality=92)
    return out.getvalue(), "image/jpeg"


def recognize(png: bytes, *, model: str, effort: str = "low", api_key: str = "") -> dict:
    """Return ``{"language", "code", "notes"}`` for the screenshot."""
    try:
        import anthropic
    except ImportError as exc:
        raise ClaudeError(t("Claude motoru için: pip install anthropic")) from exc

    data, media_type = _shrink(png)
    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    try:
        response = client.beta.messages.create(
            model=model,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={
                "effort": effort,
                "format": {"type": "json_schema", "schema": _SCHEMA},
            },
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": base64.standard_b64encode(data).decode("ascii"),
                            },
                        },
                        {"type": "text", "text": "Transcribe the code in this screenshot."},
                    ],
                }
            ],
        )
    except anthropic.AuthenticationError as exc:
        raise ClaudeError(t("Anthropic API anahtarı geçersiz veya eksik.")) from exc
    except anthropic.PermissionDeniedError as exc:
        raise ClaudeError(t("Bu anahtarın {model} modeline erişimi yok.", model=model)) from exc
    except anthropic.RateLimitError as exc:
        raise ClaudeError(t("Claude hız limitine takıldı, biraz sonra tekrar dene.")) from exc
    except anthropic.APIStatusError as exc:
        raise ClaudeError(t("Claude API hatası {status}: {message}", status=exc.status_code, message=exc.message)) from exc
    except anthropic.APIConnectionError as exc:
        raise ClaudeError(t("Claude API'ye bağlanılamadı (internet?).")) from exc
    except anthropic.AnthropicError as exc:
        raise ClaudeError(str(exc)) from exc
    except TypeError as exc:  # raised when no credentials can be resolved
        raise ClaudeError(t("Anthropic API anahtarı ayarlanmamış.")) from exc

    if response.stop_reason == "refusal":
        raise ClaudeError(t("Claude bu görüntüyü işlemeyi reddetti."))
    if response.stop_reason == "max_tokens":
        raise ClaudeError(t("Kod çok uzun, yanıt yarıda kesildi."))

    text = next((block.text for block in response.content if block.type == "text"), None)
    if text is None:
        raise ClaudeError(t("Claude boş yanıt döndü."))
    try:
        return json.loads(text)
    except ValueError as exc:
        raise ClaudeError(t("Claude yanıtı çözümlenemedi.")) from exc
