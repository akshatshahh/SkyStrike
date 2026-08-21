"""Ticket-link hygiene. Never send a fan to a known-dead or unsafe href."""

from __future__ import annotations

from urllib.parse import urlparse

from bowl import is_bowl_index

WEAK_HOMEPAGES = {
    "www.redrocksonline.com",
    "redrocksonline.com",
    "www.highergroundmusic.com",
    "highergroundmusic.com",
}


def https_url(url: str | None) -> str | None:
    text = (url or "").strip()
    if not text:
        return None
    if text.startswith("http://"):
        text = "https://" + text[len("http://") :]
    return text


def marketplace_404(url: str | None, event_id: str | None = None) -> bool:
    """Discovery's /event/Z7… Ticketmaster links 404 on the public site."""
    parsed = urlparse(url or "")
    host = (parsed.hostname or "").lower()
    if "ticketmaster." not in host:
        return False
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) != 2 or parts[0].lower() != "event":
        return False
    token = parts[1]
    if token.startswith("Z7") or token.startswith("z7"):
        return True
    return bool(event_id) and token == event_id


def is_homepage(url: str | None) -> bool:
    parsed = urlparse(url or "")
    parts = [p for p in parsed.path.split("/") if p]
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    if host in WEAK_HOMEPAGES and not parts:
        return True
    return not parts


def classify(url: str | None, event_id: str | None = None) -> str:
    """empty | unsafe | dead | index | weak | ok"""
    text = (url or "").strip()
    if not text:
        return "empty"
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"}:
        return "unsafe"
    if parsed.username or parsed.password:
        return "unsafe"
    if marketplace_404(text, event_id) or is_bowl_index(text):
        return "dead" if marketplace_404(text, event_id) else "index"
    if is_homepage(text):
        return "weak"
    return "ok"


def safe_public_url(url: str | None, event_id: str | None = None) -> str | None:
    """Only an https link we are willing to put on a stub."""
    text = https_url(url)
    kind = classify(text, event_id)
    if kind != "ok":
        return None
    return text
