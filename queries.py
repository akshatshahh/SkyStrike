from collections import Counter
from datetime import date, datetime, time
from decimal import Decimal
from urllib.parse import urlparse

from db import get_conn, init_schema


def _num(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _as_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _as_time(value) -> time | None:
    if value is None:
        return None
    if isinstance(value, time):
        return value
    if isinstance(value, datetime):
        return value.time()
    text = str(value)
    if not text:
        return None
    try:
        return time.fromisoformat(text[:8])
    except ValueError:
        return None


SYMBOLS = {"USD": "$", "CAD": "C$", "GBP": "£", "EUR": "€", "AUD": "A$", "MXN": "MX$"}


def seller_label(url: str | None) -> str:
    host = (urlparse(url or "").hostname or "").lower()
    if "ticketweb" in host:
        return "ticketweb"
    if "ticketmaster" in host:
        return "ticketmaster"
    if "livenation" in host:
        return "live nation"
    return "tickets"


def money(value: float | None, currency: str | None = "USD") -> str:
    if value is None:
        return "—"
    mark = SYMBOLS.get((currency or "USD").upper(), f"{currency} ")
    if abs(value - round(value)) < 0.001:
        return f"{mark}{int(round(value))}"
    return f"{mark}{value:,.2f}"


def clock(value: time | None) -> str:
    if value is None:
        return ""
    hour = value.hour
    minute = value.minute
    suffix = "p" if hour >= 12 else "a"
    hour12 = hour % 12 or 12
    if minute:
        return f"{hour12}:{minute:02d}{suffix}"
    return f"{hour12}{suffix}"


def when_label(local_date: date | None, local_time: time | None) -> str:
    if local_date is None:
        return ""
    day = local_date.strftime("%a")
    month = local_date.strftime("%b")
    bit = f"{day} {local_date.day} {month}"
    t = clock(local_time)
    return f"{bit} · {t}" if t else bit


def days_until(local_date: date | None, today: date | None = None) -> int | None:
    if local_date is None:
        return None
    today = today or date.today()
    return (local_date - today).days


def _delta_line(cur_lo, cur_hi, prev_lo, prev_hi) -> str | None:
    if prev_lo is None or cur_lo is None:
        return None
    d_lo = cur_lo - prev_lo
    d_hi = (cur_hi - prev_hi) if cur_hi is not None and prev_hi is not None else 0
    if abs(d_lo) < 0.5 and abs(d_hi) < 0.5:
        return "scale unchanged"
    parts = []
    if abs(d_lo) >= 0.5:
        sign = "+" if d_lo > 0 else "−"
        parts.append(f"low {sign}{money(abs(d_lo))[1:]}")
    if abs(d_hi) >= 0.5:
        sign = "+" if d_hi > 0 else "−"
        parts.append(f"high {sign}{money(abs(d_hi))[1:]}")
    return " · ".join(parts) if parts else None


def last_pull() -> dict | None:
    with get_conn() as conn:
        init_schema(conn)
        return conn.execute(
            """
            SELECT started_at, finished_at, ok, events_seen, priced_count, note
            FROM pulls
            ORDER BY started_at DESC
            LIMIT 1
            """
        ).fetchone()


def sparkline_svg(values: list[float], w: int = 88, h: int = 20) -> str:
    vals = [v for v in values if v is not None]
    if not vals:
        return ""
    if len(vals) == 1:
        return (
            f'<svg class="spark" viewBox="0 0 {w} {h}" width="{w}" height="{h}" aria-hidden="true">'
            f'<circle cx="{w * 0.5:.1f}" cy="{h * 0.5:.1f}" r="2"/></svg>'
        )
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    n = len(vals)
    pts = []
    for i, v in enumerate(vals):
        x = 2 + i * (w - 4) / (n - 1)
        y = (h - 3) - (v - lo) / span * (h - 6)
        pts.append((x, y))
    d = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    last_x, last_y = pts[-1]
    dipped = vals[-1] < vals[0] - 0.49
    color = "#9b2118" if dipped else "#1a140c"
    return (
        f'<svg class="spark" viewBox="0 0 {w} {h}" width="{w}" height="{h}" aria-hidden="true">'
        f'<polyline fill="none" stroke="{color}" stroke-width="1.4" points="{d}"/>'
        f'<circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="2" fill="{color}"/>'
        f"</svg>"
    )


def load_board() -> tuple[list[dict], dict]:
    with get_conn() as conn:
        init_schema(conn)
        rows = conn.execute(
            """
            SELECT
                e.id,
                e.name,
                e.url,
                e.attraction,
                e.local_date,
                e.local_time,
                e.status,
                e.genre,
                e.segment,
                e.image_url,
                e.currency,
                e.price_min,
                e.price_max,
                e.priced_at,
                v.name AS venue_name,
                v.city,
                v.state_code,
                prev.min_price AS prev_min,
                prev.max_price AS prev_max
            FROM events e
            LEFT JOIN venues v ON v.id = e.venue_id
            LEFT JOIN LATERAL (
                SELECT min_price, max_price
                FROM price_snapshots s
                WHERE s.event_id = e.id
                  AND (e.priced_at IS NULL OR s.captured_at < e.priced_at)
                ORDER BY s.captured_at DESC
                LIMIT 1
            ) prev ON TRUE
            WHERE e.local_date >= CURRENT_DATE
              AND COALESCE(e.status, '') NOT IN ('cancelled', 'canceled')
            ORDER BY e.local_date ASC, e.local_time ASC NULLS LAST, e.name ASC
            """
        ).fetchall()
        pull = conn.execute(
            """
            SELECT finished_at, events_seen, priced_count, ok, note
            FROM pulls
            WHERE ok = TRUE
            ORDER BY finished_at DESC
            LIMIT 1
            """
        ).fetchone()
        ids = [r["id"] for r in rows]
        history_map: dict[str, list[float]] = {i: [] for i in ids}
        if ids:
            snaps = conn.execute(
                """
                SELECT event_id, min_price
                FROM price_snapshots
                WHERE event_id = ANY(%s)
                ORDER BY event_id, captured_at ASC
                """,
                (ids,),
            ).fetchall()
            for snap in snaps:
                price = _num(snap["min_price"])
                if price is None:
                    continue
                bucket = history_map.setdefault(snap["event_id"], [])
                bucket.append(price)
                if len(bucket) > 8:
                    del bucket[:-8]

    today = date.today()
    priced_vals = []
    listings = []
    for raw in rows:
        lo = _num(raw["price_min"])
        hi = _num(raw["price_max"])
        if lo is not None:
            priced_vals.append(lo)
        if hi is not None:
            priced_vals.append(hi)
        local_date = _as_date(raw["local_date"])
        local_time = _as_time(raw["local_time"])
        days = days_until(local_date, today)
        city = raw.get("city") or ""
        state = raw.get("state_code") or ""
        currency = raw.get("currency") or "USD"
        prev_lo = _num(raw.get("prev_min"))
        history = history_map.get(raw["id"]) or []
        if lo is not None and (not history or abs(history[-1] - lo) > 0.001):
            history = history + [lo]
            history = history[-8:]
        place = ", ".join(p for p in (raw.get("venue_name"), city) if p)
        if state and city:
            place = f"{raw.get('venue_name') or '—'}, {city} {state}"
        listings.append(
            {
                "id": raw["id"],
                "name": raw["name"],
                "headline": raw.get("attraction") or raw["name"],
                "url": raw.get("url") or "",
                "venue_name": raw.get("venue_name") or "—",
                "city": city,
                "state": state,
                "place": place,
                "when": when_label(local_date, local_time),
                "days": days,
                "days_label": _days_word(days),
                "status": (raw.get("status") or "").lower(),
                "genre": raw.get("genre") or "",
                "priced": lo is not None,
                "lo": lo,
                "hi": hi if hi is not None else lo,
                "lo_label": money(lo, currency) if lo is not None else "",
                "hi_label": money(hi if hi is not None else lo, currency) if lo is not None else "",
                "same_price": lo is not None and hi is not None and abs(lo - hi) < 0.05,
                "delta": _delta_line(lo, hi, prev_lo, _num(raw.get("prev_max"))),
                "seller": seller_label(raw.get("url") or ""),
                "spark": sparkline_svg(history),
                "pulls": len(history),
            }
        )

    g_lo = min(priced_vals) if priced_vals else 0
    g_hi = max(priced_vals) if priced_vals else 1
    if g_hi <= g_lo:
        g_hi = g_lo + 1
    span = g_hi - g_lo
    for item in listings:
        if not item["priced"]:
            item["bar_left"] = 0
            item["bar_width"] = 0
            continue
        left = (item["lo"] - g_lo) / span * 100
        width = (item["hi"] - item["lo"]) / span * 100
        item["bar_left"] = round(max(0, min(left, 98)), 2)
        item["bar_width"] = round(max(1.4, min(width, 100 - item["bar_left"])), 2)

    counts = Counter(
        item["city"] for item in listings if item["city"] and item["priced"]
    )
    cities = [name for name, _n in counts.most_common(12)]

    meta = {
        "count": len(listings),
        "priced": sum(1 for x in listings if x["priced"]),
        "cities": cities,
        "pull": pull,
        "today": today.isoformat(),
    }
    return listings, meta


def filter_listings(listings: list[dict], view: str = "priced", city: str | None = None) -> list[dict]:
    if city:
        return [row for row in listings if row["city"] == city]
    if view == "week":
        return [
            row
            for row in listings
            if row["days"] is not None and 0 <= row["days"] <= 7
        ]
    if view == "all":
        return listings
    return [row for row in listings if row["priced"]]


def _days_word(days: int | None) -> str:
    if days is None:
        return ""
    if days <= 0:
        return "today"
    if days == 1:
        return "day"
    return "days"
