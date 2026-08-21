import time
from datetime import datetime, timezone

import requests

from bowl import is_bowl_index, is_bowl_venue, performance_url as bowl_performance_url
from settings import tm_key
from urls import https_url, marketplace_404, safe_public_url

BASE = "https://app.ticketmaster.com/discovery/v2"
SESSION = requests.Session()
SESSION.headers["User-Agent"] = "days-out/0.1 (discovery client)"


class TicketmasterError(RuntimeError):
    pass


def _get(path: str, params: dict) -> dict:
    key = tm_key()
    if not key:
        raise TicketmasterError("no Ticketmaster key")
    params = {**params, "apikey": key}
    url = f"{BASE}/{path}"
    last_err = None
    for attempt in range(4):
        try:
            resp = SESSION.get(url, params=params, timeout=20)
        except requests.RequestException as exc:
            last_err = exc
            time.sleep(0.6 * (attempt + 1))
            continue
        if resp.status_code == 429:
            time.sleep(1.2 * (attempt + 1))
            continue
        if resp.status_code >= 400:
            raise TicketmasterError(f"{resp.status_code} from {path}: {resp.text[:240]}")
        return resp.json()
    raise TicketmasterError(f"gave up on {path}: {last_err}")


def search_venues(keyword: str, size: int = 8) -> list[dict]:
    data = _get(
        "venues.json",
        {
            "keyword": keyword,
            "countryCode": "US",
            "size": size,
        },
    )
    return ((data.get("_embedded") or {}).get("venues")) or []


def best_venue_match(keyword: str, hint_id: str | None = None) -> dict | None:
    if hint_id:
        try:
            data = _get(f"venues/{hint_id}.json", {})
            if data.get("id"):
                return data
        except TicketmasterError:
            pass
    needle = keyword.strip().lower()
    hits = search_venues(keyword)
    if not hits:
        return None
    for v in hits:
        if (v.get("name") or "").strip().lower() == needle:
            return v
    return hits[0]


def search_events(**params) -> list[dict]:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    query = {
        "size": 20,
        "sort": "date,asc",
        "countryCode": "US",
        "startDateTime": now,
        "includeTBA": "no",
        "includeTBD": "no",
        **params,
    }
    data = _get("events.json", query)
    return ((data.get("_embedded") or {}).get("events")) or []


def _venue_name(raw: dict) -> str | None:
    venues = ((raw.get("_embedded") or {}).get("venues")) or []
    if not venues:
        return None
    return (venues[0].get("name") or "").strip() or None


def _local_date(raw: dict) -> str | None:
    start = ((raw.get("dates") or {}).get("start")) or {}
    return start.get("localDate")


def enrich_url(parsed: dict) -> None:
    """Search sometimes omits outlets; recover a URL that actually opens."""
    url = parsed.get("url")
    if url and not marketplace_404(url, parsed.get("id")) and not is_bowl_index(url):
        return
    try:
        detail = _get(f"events/{parsed['id']}.json", {})
        time.sleep(0.25)
        parsed["url"] = pick_event_url(detail) or parsed.get("url")
    except TicketmasterError:
        pass
    venue = (parsed.get("venue") or {}).get("name") if isinstance(parsed.get("venue"), dict) else None
    if is_bowl_venue(venue) and (
        not parsed.get("url") or marketplace_404(parsed.get("url"), parsed.get("id")) or is_bowl_index(parsed.get("url"))
    ):
        bowl = bowl_performance_url(parsed.get("local_date"), parsed.get("name"))
        if bowl:
            parsed["url"] = bowl


def pick_event_url(raw: dict) -> str | None:
    event_id = raw.get("id")
    url = https_url(raw.get("url"))
    outlets = raw.get("outlets") or []
    box = next(
        (
            https_url(item.get("url"))
            for item in outlets
            if (item.get("type") or "") == "venueBoxOffice" and item.get("url")
        ),
        None,
    )
    chosen = None
    if url and not marketplace_404(url, event_id) and not is_bowl_index(url):
        chosen = url
    elif is_bowl_venue(_venue_name(raw)):
        chosen = bowl_performance_url(_local_date(raw), raw.get("name"))
    if not chosen and box and not is_bowl_index(box):
        chosen = box
    if not chosen and url and not marketplace_404(url, event_id):
        chosen = url
    return safe_public_url(chosen, event_id)


def pick_image(images: list[dict]) -> str | None:
    if not images:
        return None
    usable = [img for img in images if not img.get("fallback")]
    pool = usable or images
    pool = sorted(pool, key=lambda img: img.get("width") or 0, reverse=True)
    wide = [img for img in pool if img.get("ratio") == "16_9"]
    chosen = (wide or pool)[0]
    url = chosen.get("url") or ""
    return url.replace("http://", "https://") or None


def _nested_name(obj: dict | None, *keys: str) -> str | None:
    cur = obj or {}
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    if isinstance(cur, str) and cur.strip():
        return cur.strip()
    return None


def parse_event(raw: dict) -> dict | None:
    event_id = raw.get("id")
    name = (raw.get("name") or "").strip()
    if not event_id or not name:
        return None

    dates = raw.get("dates") or {}
    start = dates.get("start") or {}
    if start.get("dateTBD"):
        return None
    local_date = start.get("localDate")
    if not local_date:
        return None

    status = ((dates.get("status") or {}).get("code") or "").lower() or None
    if status in {"cancelled", "canceled"}:
        return None

    venues = ((raw.get("_embedded") or {}).get("venues")) or []
    venue_raw = venues[0] if venues else {}
    venue = parse_venue(venue_raw) if venue_raw.get("id") else None

    attractions = ((raw.get("_embedded") or {}).get("attractions")) or []
    attraction = None
    if attractions:
        attraction = (attractions[0].get("name") or "").strip() or None

    classifications = raw.get("classifications") or []
    primary = next((c for c in classifications if c.get("primary")), None)
    klass = primary or (classifications[0] if classifications else {})
    genre = _nested_name(klass, "genre", "name")
    segment = _nested_name(klass, "segment", "name")

    ranges = raw.get("priceRanges") or []
    chosen = next((p for p in ranges if (p.get("type") or "").lower() == "standard"), None)
    if chosen is None and ranges:
        chosen = ranges[0]
    price_min = price_max = currency = range_type = None
    if chosen:
        try:
            price_min = float(chosen["min"]) if chosen.get("min") is not None else None
            price_max = float(chosen["max"]) if chosen.get("max") is not None else None
        except (TypeError, ValueError):
            price_min = price_max = None
        currency = chosen.get("currency")
        range_type = chosen.get("type")
        if (price_min or 0) <= 0 and (price_max or 0) <= 0:
            price_min = price_max = currency = range_type = None

    local_time = start.get("localTime")
    datetime_utc = start.get("dateTime")

    return {
        "id": event_id,
        "name": name,
        "url": pick_event_url(raw),
        "attraction": attraction,
        "venue": venue,
        "local_date": local_date,
        "local_time": local_time,
        "datetime_utc": datetime_utc,
        "status": status,
        "genre": genre,
        "segment": segment,
        "image_url": pick_image(raw.get("images") or []),
        "currency": currency,
        "price_min": price_min,
        "price_max": price_max,
        "range_type": range_type,
    }


def parse_venue(raw: dict) -> dict:
    loc = raw.get("location") or {}
    lat = lon = None
    try:
        lat = float(loc["latitude"]) if loc.get("latitude") is not None else None
        lon = float(loc["longitude"]) if loc.get("longitude") is not None else None
    except (TypeError, ValueError):
        pass
    return {
        "id": raw["id"],
        "name": (raw.get("name") or "").strip() or raw["id"],
        "city": _nested_name(raw, "city", "name"),
        "state_code": _nested_name(raw, "state", "stateCode"),
        "country_code": _nested_name(raw, "country", "countryCode"),
        "address": _nested_name(raw, "address", "line1"),
        "postal_code": raw.get("postalCode"),
        "timezone": raw.get("timezone"),
        "latitude": lat,
        "longitude": lon,
    }
