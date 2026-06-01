"""
Shared headed Playwright browser session for reading Reddit without the API.

Reddit blocks unauthenticated requests to its `.json` endpoints when they come
from plain HTTP clients (requests/curl) or headless browsers. A *headed* real
Chromium browser, however, automatically solves Reddit's JavaScript challenge,
receives a clearance, and can then read the `.json` endpoints normally.

This module exposes a single, lazily-created browser session that both the data
fetcher (reddit/jsonapi.py) and the screenshot downloader can share, so the JS
challenge only has to be solved once per run.
"""

import json
import re
from typing import Optional

from playwright.sync_api import sync_playwright

from utils import settings

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36"
)

# module-level singletons
_pw = None
_browser = None
_context = None
_warmed = False


def _headless() -> bool:
    """Reddit's JS challenge requires a headed browser to be solved reliably."""
    # Allow override via config; default to headed (False) for reliability.
    try:
        return bool(settings.config["settings"].get("headless_reddit", False))
    except Exception:
        return False


def get_context():
    """Return a shared Playwright BrowserContext, creating it on first use."""
    global _pw, _browser, _context
    if _context is not None:
        return _context

    _pw = sync_playwright().start()
    _browser = _pw.chromium.launch(headless=_headless())
    _context = _browser.new_context(
        locale="en-US,en;q=0.9",
        user_agent=_USER_AGENT,
        viewport={"width": 1280, "height": 1080},
    )
    return _context


def _warmup(context):
    """Visit reddit.com once so the JS challenge is solved for this session."""
    global _warmed
    if _warmed:
        return
    page = context.new_page()
    try:
        page.goto("https://www.reddit.com/", timeout=60000, wait_until="domcontentloaded")
        # give the JS challenge a moment to resolve
        page.wait_for_timeout(4000)
        _warmed = True
    finally:
        page.close()


def fetch_json(url: str) -> dict:
    """
    Fetch a Reddit `.json` URL through the headed browser session and return the
    parsed JSON. Solves the JS challenge on first use.
    """
    context = get_context()
    _warmup(context)

    page = context.new_page()
    try:
        page.goto(url, timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        body = page.content()
    finally:
        page.close()

    # The JSON is rendered inside the page; extract it from the <pre> or body.
    text = _extract_json_text(body)
    return json.loads(text)


def _extract_json_text(html: str) -> str:
    """Pull the raw JSON string out of the browser-rendered HTML page."""
    # Browsers wrap raw JSON responses in <pre>...</pre>
    m = re.search(r"<pre[^>]*>(.*?)</pre>", html, re.DOTALL)
    if m:
        raw = m.group(1)
    else:
        # Fallback: strip the outer body tags
        m2 = re.search(r"<body[^>]*>(.*?)</body>", html, re.DOTALL)
        raw = m2.group(1) if m2 else html
    # Unescape HTML entities the browser may have inserted
    raw = (
        raw.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#34;", '"')
        .replace("&#39;", "'")
    )
    # Strip any stray tags (e.g. syntax-highlight spans) just in case
    raw = re.sub(r"<[^>]+>", "", raw)
    return raw.strip()


def close():
    """Tear down the shared browser session."""
    global _pw, _browser, _context, _warmed
    try:
        if _context is not None:
            _context.close()
        if _browser is not None:
            _browser.close()
        if _pw is not None:
            _pw.stop()
    finally:
        _pw = _browser = _context = None
        _warmed = False
