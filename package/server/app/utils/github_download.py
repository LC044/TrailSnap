"""GitHub URL mirrors shared by server-side update and railway downloads."""
from __future__ import annotations

import asyncio
from urllib.parse import urlsplit

MIRROR_PREFIXES = ("https://gh-proxy.com/", "https://gh-proxy.at9.net/")
GITHUB_HOSTS = {"github.com", "api.github.com", "raw.githubusercontent.com"}
DOWNLOAD_ROUNDS = 3
RETRY_BASE_DELAY = 0.5


def github_url_candidates(url: str) -> list[str]:
    """Return mirror candidates for GitHub URLs, followed by the origin.

    Existing proxy prefixes are normalized first so retries never nest them.
    Non-GitHub hosts are returned unchanged.
    """
    original = url
    for prefix in MIRROR_PREFIXES:
        if original.startswith(prefix):
            original = original[len(prefix):]
            break
    if urlsplit(original).hostname not in GITHUB_HOSTS or not original.startswith("https://"):
        return [url]
    return [*(prefix + original for prefix in MIRROR_PREFIXES), original]


async def retry_backoff(round_number: int) -> None:
    if round_number:
        await asyncio.sleep(RETRY_BASE_DELAY * (2 ** (round_number - 1)))
