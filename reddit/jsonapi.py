"""
Lightweight Reddit data fetcher that uses the public reddit.com `.json`
endpoints instead of the official Reddit API (PRAW / OAuth).

The objects returned here mimic the small subset of the PRAW interface that the
rest of this project relies on, so they can be used as drop-in replacements for
`praw` Submission / Comment objects:

    Submission: .id .title .selftext .score .upvote_ratio .num_comments
                .over_18 .stickied .is_self .permalink .author .comments
                str(submission) -> id

    Comment:    .id .body .permalink .author .stickied  (no MoreComments)

No credentials are required to read this data.
"""

from typing import List, Optional
from urllib.parse import urlencode

from utils import reddit_browser

_BASE = "https://www.reddit.com"


class _Author:
    """Mimics praw's redditor object: bool() / str() works, never None-crashes."""

    def __init__(self, name: Optional[str]):
        self.name = name

    def __str__(self):
        return self.name or "[deleted]"

    def __bool__(self):
        return bool(self.name) and self.name != "[deleted]"


class Comment:
    def __init__(self, data: dict):
        self.id = data.get("id", "")
        self.body = data.get("body", "")
        self.permalink = data.get("permalink", "")
        self.stickied = bool(data.get("stickied", False))
        author = data.get("author")
        self.author = _Author(author) if author and author != "[deleted]" else None

    def __str__(self):
        return self.id


class Submission:
    def __init__(self, data: dict):
        self._data = data
        self.id = data.get("id", "")
        self.title = data.get("title", "")
        self.selftext = data.get("selftext", "") or ""
        self.score = data.get("score", 0)
        self.upvote_ratio = data.get("upvote_ratio", 0)
        self.num_comments = data.get("num_comments", 0)
        self.over_18 = bool(data.get("over_18", False))
        self.stickied = bool(data.get("stickied", False))
        self.is_self = bool(data.get("is_self", False))
        self.permalink = data.get("permalink", "")
        author = data.get("author")
        self.author = _Author(author) if author and author != "[deleted]" else None
        self._comments: Optional[List[Comment]] = None

    @property
    def comments(self) -> List[Comment]:
        """Lazily fetch top-level comments for this submission."""
        if self._comments is None:
            self._comments = _fetch_comments(self.id)
        return self._comments

    def __str__(self):
        return self.id


def _get_json(url: str, params: dict = None) -> dict:
    """Fetch JSON via the shared headed browser session (bypasses Reddit's
    JS challenge that blocks plain HTTP clients)."""
    if params:
        url = f"{url}?{urlencode(params)}"
    return reddit_browser.fetch_json(url)


def _listing_to_submissions(listing: dict) -> List[Submission]:
    children = listing.get("data", {}).get("children", [])
    return [Submission(c["data"]) for c in children if c.get("kind") == "t3"]


def _fetch_comments(post_id: str) -> List[Comment]:
    """Fetch top-level comments for a post id (without the leading t3_)."""
    pid = post_id.replace("t3_", "")
    data = _get_json(f"{_BASE}/comments/{pid}.json", params={"raw_json": 1, "limit": 100})
    # data[0] is the post listing, data[1] is the comment listing
    if not isinstance(data, list) or len(data) < 2:
        return []
    children = data[1].get("data", {}).get("children", [])
    comments = []
    for c in children:
        if c.get("kind") != "t1":  # skip "more" (MoreComments equivalent)
            continue
        comments.append(Comment(c["data"]))
    return comments


class Subreddit:
    """Mimics praw's subreddit helper for the methods this project uses."""

    def __init__(self, name: str):
        # supports multi-subreddit syntax like "AskReddit+nosleep"
        self.display_name = name

    def hot(self, limit: int = 25) -> List[Submission]:
        data = _get_json(
            f"{_BASE}/r/{self.display_name}/hot.json",
            params={"limit": limit, "raw_json": 1},
        )
        return _listing_to_submissions(data)

    def top(self, time_filter: str = "day", limit: int = 25) -> List[Submission]:
        data = _get_json(
            f"{_BASE}/r/{self.display_name}/top.json",
            params={"t": time_filter, "limit": limit, "raw_json": 1},
        )
        return _listing_to_submissions(data)


class RedditClient:
    """Replacement for the praw.Reddit object (read-only, no auth)."""

    def subreddit(self, name: str) -> Subreddit:
        return Subreddit(name)

    def submission(self, id: str) -> Submission:
        pid = id.replace("t3_", "")
        data = _get_json(f"{_BASE}/comments/{pid}.json", params={"raw_json": 1, "limit": 1})
        if not isinstance(data, list) or not data:
            raise RuntimeError(f"Could not fetch submission {id}")
        post_data = data[0]["data"]["children"][0]["data"]
        return Submission(post_data)
