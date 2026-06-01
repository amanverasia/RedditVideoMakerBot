#!/usr/bin/env python
"""Standalone harness: regenerate ONLY the TTS mp3s from cached reddit_object.
No Reddit fetch, no screenshots, no render."""
import os
os.environ.setdefault("translators_default_region", "EN")
import json

from utils import settings
settings.check_toml("utils/.config.template.toml", "config.toml")

from video_creation.voices import save_text_to_mp3

RID = "1ttnna4"
reddit_object = json.load(open(f"assets/temp/{RID}/reddit_object.json", encoding="utf-8"))

# Move stale per-clip mp3s aside (don't delete) so we don't mix old (broken)
# clips with new ones. They land in mp3/_old_<n>/ for safekeeping.
import glob, shutil
bak = f"assets/temp/{RID}/mp3/_old"
os.makedirs(bak, exist_ok=True)
for f in glob.glob(f"assets/temp/{RID}/mp3/*.mp3"):
    shutil.move(f, os.path.join(bak, os.path.basename(f)))

length, n = save_text_to_mp3(reddit_object)
print(f"TTS_DONE length={length} comments={n}")
