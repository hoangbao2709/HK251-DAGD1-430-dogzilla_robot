from __future__ import annotations

import re
from typing import Final


DEFAULT_VOICE: Final[str] = "vi-VN-HoaiMyNeural"
VOICE_GENDER: Final[str] = "female"


async def synthesize_vietnamese_speech(
    text: str,
    *,
    voice: str = DEFAULT_VOICE,
) -> bytes:
    try:
        import edge_tts  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("edge-tts is not installed") from exc

    if voice != DEFAULT_VOICE:
        voice = DEFAULT_VOICE

    ssml_text = re.sub(r"\s+", " ", text).strip()
    communicate = edge_tts.Communicate(
        text=ssml_text,
        voice=voice,
        rate="-4%",
        pitch="+22Hz",
        volume="+0%",
    )

    audio_parts: list[bytes] = []
    async for chunk in communicate.stream():
        if chunk.get("type") == "audio" and chunk.get("data"):
            audio_parts.append(chunk["data"])

    if not audio_parts:
        raise RuntimeError("TTS service returned empty audio")

    return b"".join(audio_parts)
