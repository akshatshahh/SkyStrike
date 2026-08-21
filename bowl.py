"""Resolve Hollywood Bowl nights to the official performance page.

Discovery's Ticketmaster /event/Z7… links 404. The venueBoxOffice outlet is
only the calendar index, which does not open a show. The Bowl publishes a
public performances API with the real URL.
"""

from __future__ import annotations

import time
from urllib.parse import urlparse

import requests

BOWL_API = "https://www.hollywoodbowl.com/api/performances"
SKIP_BITS = (
    "parking",
    "shuttle",
    "park & ride",
    "park and ride",
    "gometro",
)

_SESSION = requests.Session()
_SESSION.headers["User-Agent"] = "days-out/0.1 (bowl calendar)"
_CACHE: list[dict] | None = None
_CACHED_AT = 0.0


def is_bowl_venue(name: str | None) -> bool:
    return "hollywood bowl" in (name or "").lower()


def is_bowl_index(url: str | None) -> bool:
    parsed = urlparse(url or "")
    host = (parsed.hostname or "").lower()
    if "hollywoodbowl.com" not in host:
        return False
    parts = [p for p in parsed.path.split("/") if p]
    return parts == ["events", "performances"] or not parts


def _shows() -> list[dict]:
    global _CACHE, _CACHED_AT
    now = time.time()
    if _CACHE is not None and now - _CACHED_AT < 3600:
        return _CACHE
    rows: list[dict] = []
    url: str | None = BOWL_API
    try:
        while url:
            data = _SESSION.get(url, timeout=20).json()
            rows.extend(data.get("results") or [])
            url = data.get("next")
            if len(rows) > 500:
                break
    except (requests.RequestException, ValueError):
        return _CACHE or []
    _CACHE = rows
    _CACHED_AT = now
    return rows


def _program_name(row: dict) -> str:
    program = row.get("program") or {}
    text = program.get("name") or ""
    return text.replace("<br>", " ").replace("&amp;", "&")


def _skip(name: str) -> bool:
    lower = name.lower()
    return any(bit in lower for bit in SKIP_BITS)


def performance_url(local_date: str | None, event_name: str | None = None) -> str | None:
    if not local_date:
        return None
    day = str(local_date)[:10]
    hits = []
    for row in _shows():
        when = (row.get("perf_time") or "")[:10]
        if when != day:
            continue
        title = _program_name(row)
        if _skip(title):
            continue
        href = row.get("performance_url") or row.get("buy_url")
        if href:
            hits.append((title, href))
    if not hits:
        return None
    if len(hits) == 1:
        return hits[0][1]
    needle = (event_name or "").strip().lower()
    if needle:
        for title, href in hits:
            if needle in title.lower() or title.lower() in needle:
                return href
    return hits[0][1]
