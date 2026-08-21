"""Audit every upcoming ticket stub.

  python check_urls.py           # pattern check (no live HTTP)
  python check_urls.py --probe   # also GET non-Ticketmaster hosts

Paste the DEAD / INDEX / WEAK / EMPTY sections back if something looks wrong.
Exit code 1 if any DEAD marketplace link is still stored.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from urllib.parse import urlparse

import requests

from db import get_conn, init_schema
from urls import classify

SKIP_PROBE_HOSTS = ("ticketmaster.", "axs.com", "seatgeek.com")


def load_rows() -> list[dict]:
    with get_conn() as conn:
        init_schema(conn)
        return conn.execute(
            """
            SELECT e.id, e.name, e.url, e.local_date, v.name AS venue, v.city
            FROM events e
            LEFT JOIN venues v ON v.id = e.venue_id
            WHERE e.local_date >= CURRENT_DATE
            ORDER BY e.local_date, e.name
            """
        ).fetchall()


def probe(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if any(bit in host for bit in SKIP_PROBE_HOSTS):
        return "skip (bot wall)"
    try:
        resp = requests.get(
            url,
            timeout=12,
            allow_redirects=True,
            headers={"User-Agent": "days-out-url-check/0.1"},
        )
        return str(resp.status_code)
    except requests.RequestException as exc:
        return type(exc).__name__


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", action="store_true")
    args = parser.parse_args()

    rows = load_rows()
    buckets: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        kind = classify(row.get("url"), row["id"])
        item = dict(row)
        item["kind"] = kind
        if args.probe and kind in {"ok", "weak", "index"} and row.get("url"):
            item["http"] = probe(row["url"])
        buckets[kind].append(item)

    print(f"upcoming {len(rows)}")
    for kind in ("dead", "index", "unsafe", "weak", "empty", "ok"):
        print(f"  {kind:7} {len(buckets[kind])}")

    for kind in ("dead", "index", "unsafe", "weak", "empty"):
        items = buckets[kind]
        if not items:
            continue
        print(f"\n## {kind.upper()} ({len(items)})")
        for item in items:
            extra = f"  http={item['http']}" if item.get("http") else ""
            place = ", ".join(p for p in (item.get("venue"), item.get("city")) if p)
            print(
                f"- {item['local_date']}  {item['name']}"
                f"{'  ·  ' + place if place else ''}"
                f"\n  {item.get('url') or '(no url)'}{extra}"
            )

    if args.probe:
        bad_http = [
            item
            for item in buckets["ok"]
            if item.get("http") and item["http"] not in {"200", "202", "skip (bot wall)"}
        ]
        if bad_http:
            print(f"\n## PROBE FAILED ({len(bad_http)})")
            for item in bad_http:
                print(f"- {item['name']}\n  {item['http']}  {item['url']}")

    dead = len(buckets["dead"]) + len(buckets["unsafe"])
    if dead:
        print(f"\nFAIL: {dead} stub(s) must not be on the board.")
        return 1
    print("\nPASS: no marketplace 404 or unsafe stubs stored.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
