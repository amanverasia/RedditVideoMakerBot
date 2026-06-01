#!/usr/bin/env python
"""Standalone harness: run ONLY make_final_video from cached assets.
No Reddit, no screenshots, no TTS, no background download."""
import os
os.environ.setdefault("translators_default_region", "EN")
import json
import math
from pathlib import Path

from utils.ffmpeg_bootstrap import ensure_ffmpeg
ensure_ffmpeg()

from utils import settings
settings.check_toml("utils/.config.template.toml", "config.toml")

from video_creation.final_video import make_final_video
from video_creation.background import get_background_config, chop_background

RID = "1ttnna4"
reddit_object = json.load(open(f"assets/temp/{RID}/reddit_object.json", encoding="utf-8"))
# Use the number of TTS clips actually generated (the wrapper caps total length
# at ~50s), NOT the number of screenshots — otherwise video/audio desync.
import re as _re
number_of_comments = len(
    [f for f in os.listdir(f"assets/temp/{RID}/mp3") if _re.fullmatch(r"\d+\.mp3", f)]
)

# length must match the TTS audio so video/audio don't drift. Compute it from
# the sum of the per-clip TTS mp3s (title + comments), which is exactly what
# make_final_video uses to lay out the overlays.
import subprocess, shutil
def dur(p):
    out = subprocess.run([shutil.which("ffprobe"), "-v", "quiet", "-show_entries",
                          "format=duration", "-of", "csv=p=0", p], capture_output=True, text=True).stdout.strip()
    try: return float(out)
    except: return 0.0

tts_total = dur(f"assets/temp/{RID}/mp3/title.mp3")
for i in range(number_of_comments):
    tts_total += dur(f"assets/temp/{RID}/mp3/{i}.mp3")
length = math.ceil(tts_total)

bg_config = {
    "video": get_background_config("video"),
    "audio": get_background_config("audio"),
}
print(f"Re-chopping background to {length}s and rendering: comments={number_of_comments}")
# Re-chop the background so it is at least as long as the TTS audio.
chop_background(bg_config, length, reddit_object)
make_final_video(number_of_comments, length, reddit_object, bg_config)
print("RENDER_DONE")
