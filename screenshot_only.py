#!/usr/bin/env python
"""Standalone harness: run ONLY the screenshot stage from cached reddit_object.
No TTS, no background download, no render. Re-uses the cached reddit_object.json
so we don't re-fetch Reddit data (still needs the browser for screenshots)."""
import os
os.environ.setdefault("translators_default_region", "EN")
import json

from utils import settings
settings.check_toml("utils/.config.template.toml", "config.toml")

from video_creation.screenshot_downloader import get_screenshots_of_reddit_posts
from utils import reddit_browser

RID = "1ttnna4"
reddit_object = json.load(open(f"assets/temp/{RID}/reddit_object.json", encoding="utf-8"))
num = len(reddit_object["comments"])
print(f"Screenshotting {num} comments...")
try:
    get_screenshots_of_reddit_posts(reddit_object, num)
    print("SCREENSHOT_DONE")
finally:
    reddit_browser.close()
