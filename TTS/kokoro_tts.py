import os
import random
import subprocess
import tempfile

import numpy as np
import soundfile as sf

from utils import settings


def _ffmpeg_path():
    """Prefer the bundled imageio-ffmpeg binary; fall back to system ffmpeg."""
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"

# Kokoro-82M voices (https://huggingface.co/hexgrad/Kokoro-82M)
# Prefix legend: a=American, b=British | f=female, m=male
voices = [
    "af_heart",
    "af_bella",
    "af_nicole",
    "af_sarah",
    "af_sky",
    "am_adam",
    "am_michael",
    "bf_emma",
    "bf_isabella",
    "bm_george",
    "bm_lewis",
]

# Map config post_lang prefixes to Kokoro lang_code.
# 'a' = American English, 'b' = British English.
_LANG_CODE = "a"


class Kokoro:
    """Local neural TTS using hexgrad/Kokoro-82M (runs offline, no API)."""

    def __init__(self):
        # Kokoro chunks long text internally via its pipeline, so we set a high
        # limit. NOTE: this MUST be > 0 — the engine_wrapper treats any comment
        # longer than max_chars as needing split_post(), and split_post() builds
        # a regex `{0,max_chars}`; with max_chars=0 that produces empty/garbled
        # audio for every comment. A large value sends comments straight to the
        # TTS engine intact.
        self.max_chars = 5000
        self.voices = voices
        self._pipeline = None

    def _get_pipeline(self):
        if self._pipeline is None:
            from kokoro import KPipeline

            lang = settings.config["reddit"]["thread"].get("post_lang") or ""
            lang_code = "b" if str(lang).lower().startswith("en-gb") else _LANG_CODE
            self._pipeline = KPipeline(lang_code=lang_code)
        return self._pipeline

    def run(self, text, filepath, random_voice: bool = False):
        if random_voice:
            voice = self.randomvoice()
        else:
            voice = settings.config["settings"]["tts"].get("kokoro_voice") or "af_heart"
            if voice not in voices:
                voice = "af_heart"

        pipeline = self._get_pipeline()
        # speed is configurable; default 1.0
        speed = float(settings.config["settings"]["tts"].get("kokoro_speed", 1.0) or 1.0)

        audio_chunks = []
        for _, _, audio in pipeline(text, voice=voice, speed=speed):
            audio_chunks.append(audio)

        if not audio_chunks:
            full_audio = np.zeros(2400, dtype=np.float32)
        else:
            full_audio = np.concatenate(audio_chunks)

        # Kokoro outputs 24kHz float audio. soundfile can't reliably write MP3,
        # so write a temp WAV and transcode to the requested path via ffmpeg.
        if filepath.lower().endswith(".wav"):
            sf.write(filepath, full_audio, 24000)
            return

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_wav = tmp.name
        try:
            sf.write(tmp_wav, full_audio, 24000)
            ffmpeg_exe = _ffmpeg_path()
            subprocess.run(
                [ffmpeg_exe, "-y", "-i", tmp_wav, filepath],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        finally:
            if os.path.exists(tmp_wav):
                os.remove(tmp_wav)

    def randomvoice(self):
        return random.choice(self.voices)
