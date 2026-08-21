"""Pull upcoming nights from Ticketmaster and snapshot the printed scale."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from db import get_conn, init_schema
from ticketmaster import (
    best_venue_match,
    enrich_url,
    parse_event,
    search_events,
)
from watchlist import ARTISTS, EVENTS_PER_QUERY, SEARCHES, VENUES

SLEEP = 0.25


def _utc_now():
    return datetime.now(timezone.utc)


def _upsert_venue(cur, venue: dict) -> None:
    cur.execute(
        """
        INSERT INTO venues (
            id, name, city, state_code, country_code, address,
            postal_code, timezone, latitude, longitude, updated_at
        )
        VALUES (
            %(id)s, %(name)s, %(city)s, %(state_code)s, %(country_code)s,
            %(address)s, %(postal_code)s, %(timezone)s, %(latitude)s,
            %(longitude)s, NOW()
        )
        ON CONFLICT (id) DO UPDATE SET
            name = EXCLUDED.name,
            city = EXCLUDED.city,
            state_code = EXCLUDED.state_code,
            country_code = EXCLUDED.country_code,
            address = EXCLUDED.address,
            postal_code = EXCLUDED.postal_code,
            timezone = EXCLUDED.timezone,
            latitude = EXCLUDED.latitude,
            longitude = EXCLUDED.longitude,
            updated_at = NOW()
        """,
        venue,
    )


def _upsert_event(cur, event: dict) -> None:
    cur.execute(
        """
        INSERT INTO events (
            id, name, url, attraction, venue_id, local_date, local_time,
            datetime_utc, status, genre, segment, image_url, currency,
            price_min, price_max, priced_at, updated_at
        )
        VALUES (
            %(id)s, %(name)s, %(url)s, %(attraction)s, %(venue_id)s,
            %(local_date)s, %(local_time)s, %(datetime_utc)s, %(status)s,
            %(genre)s, %(segment)s, %(image_url)s, %(currency)s,
            %(price_min)s, %(price_max)s, %(priced_at)s, NOW()
        )
        ON CONFLICT (id) DO UPDATE SET
            name = EXCLUDED.name,
            url = EXCLUDED.url,
            attraction = EXCLUDED.attraction,
            venue_id = COALESCE(EXCLUDED.venue_id, events.venue_id),
            local_date = EXCLUDED.local_date,
            local_time = EXCLUDED.local_time,
            datetime_utc = EXCLUDED.datetime_utc,
            status = EXCLUDED.status,
            genre = EXCLUDED.genre,
            segment = EXCLUDED.segment,
            image_url = COALESCE(EXCLUDED.image_url, events.image_url),
            currency = EXCLUDED.currency,
            price_min = EXCLUDED.price_min,
            price_max = EXCLUDED.price_max,
            priced_at = EXCLUDED.priced_at,
            updated_at = NOW()
        """,
        event,
    )


def _snapshot(cur, event: dict) -> None:
    if event["price_min"] is None and event["price_max"] is None:
        return
    cur.execute(
        """
        INSERT INTO price_snapshots (
            event_id, captured_at, currency, min_price, max_price, range_type
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            event["id"],
            event["priced_at"],
            event["currency"],
            event["price_min"],
            event["price_max"],
            event["range_type"],
        ),
    )


def _stash(bucket: dict, raw: dict) -> None:
    parsed = parse_event(raw)
    if parsed and parsed["id"] not in bucket:
        enrich_url(parsed)
        bucket[parsed["id"]] = parsed


def collect() -> dict[str, dict]:
    bucket: dict[str, dict] = {}

    for spec in VENUES:
        venue = best_venue_match(spec["name"], spec.get("id") or None)
        time.sleep(SLEEP)
        if not venue:
            continue
        events = search_events(
            venueId=venue["id"],
            size=EVENTS_PER_QUERY,
            classificationName="music",
        )
        for raw in events:
            _stash(bucket, raw)
        time.sleep(SLEEP)

    for artist in ARTISTS:
        events = search_events(keyword=artist, size=EVENTS_PER_QUERY, classificationName="music")
        for raw in events:
            _stash(bucket, raw)
        time.sleep(SLEEP)

    for extra in SEARCHES:
        events = search_events(**extra)
        for raw in events:
            _stash(bucket, raw)
        time.sleep(SLEEP)
        later = (_utc_now() + timedelta(days=12)).strftime("%Y-%m-%dT%H:%M:%SZ")
        events = search_events(**{**extra, "startDateTime": later, "size": min(int(extra.get("size") or 20), 40)})
        for raw in events:
            _stash(bucket, raw)
        time.sleep(SLEEP)

    return bucket


def persist(events: dict[str, dict]) -> tuple[int, int]:
    priced_at = _utc_now()
    priced = 0
    with get_conn() as conn:
        init_schema(conn)
        cur = conn.cursor()
        for parsed in events.values():
            venue = parsed.get("venue")
            if venue:
                _upsert_venue(cur, venue)
            row = {
                "id": parsed["id"],
                "name": parsed["name"],
                "url": parsed.get("url"),
                "attraction": parsed.get("attraction"),
                "venue_id": venue["id"] if venue else None,
                "local_date": parsed.get("local_date"),
                "local_time": parsed.get("local_time") or None,
                "datetime_utc": parsed.get("datetime_utc"),
                "status": parsed.get("status"),
                "genre": parsed.get("genre"),
                "segment": parsed.get("segment"),
                "image_url": parsed.get("image_url"),
                "currency": parsed.get("currency"),
                "price_min": parsed.get("price_min"),
                "price_max": parsed.get("price_max"),
                "priced_at": priced_at if parsed.get("price_min") is not None else None,
                "range_type": parsed.get("range_type"),
            }
            _upsert_event(cur, row)
            if row["price_min"] is not None:
                _snapshot(cur, row)
                priced += 1
    return len(events), priced


def last_pull_age_seconds(conn=None) -> float | None:
    from db import connect, init_schema

    own = conn is None
    if own:
        try:
            conn = connect()
        except Exception:
            return None
        init_schema(conn)
        conn.commit()
    try:
        row = conn.execute(
            """
            SELECT EXTRACT(EPOCH FROM (NOW() - finished_at)) AS age
            FROM pulls
            WHERE ok = TRUE AND finished_at IS NOT NULL
            ORDER BY finished_at DESC
            LIMIT 1
            """
        ).fetchone()
        if not row or row["age"] is None:
            return None
        return float(row["age"])
    except Exception:
        return None
    finally:
        if own:
            conn.close()


def run(note: str = "manual") -> dict:
    started = _utc_now()
    events_seen = priced_count = 0
    ok = False
    error = None
    try:
        events = collect()
        events_seen, priced_count = persist(events)
        ok = True
    except Exception as exc:
        error = str(exc)
    try:
        with get_conn() as conn:
            init_schema(conn)
            conn.execute(
                """
                INSERT INTO pulls (
                    started_at, finished_at, ok, events_seen, priced_count, note
                )
                VALUES (%s, NOW(), %s, %s, %s, %s)
                """,
                (started, ok, events_seen, priced_count, error or note),
            )
    except Exception:
        pass
    return {
        "ok": ok,
        "events_seen": events_seen,
        "priced_count": priced_count,
        "note": error or note,
    }


def maybe_refresh(max_age_hours: float = 3.0) -> dict | None:
    """Refresh if the last good pull is older than max_age_hours, or missing."""
    from db import connect, init_schema as _init

    try:
        conn = connect()
    except Exception:
        return None
    try:
        _init(conn)
        conn.commit()
        conn.execute("SELECT pg_advisory_lock(%s)", (81421,))
        try:
            age = last_pull_age_seconds(conn)
            if age is not None and age < max_age_hours * 3600:
                return None
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (81421,))
            conn.commit()
    finally:
        conn.close()
    return run(note="stale")


if __name__ == "__main__":
    result = run(note="cli")
    print(
        f"pulled {result['events_seen']} listings, "
        f"{result['priced_count']} with a scale"
    )
    if not result["ok"]:
        raise SystemExit(result["note"] or 1)
