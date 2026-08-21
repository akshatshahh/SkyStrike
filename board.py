from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import quote

from jinja2 import Environment, FileSystemLoader, select_autoescape

from queries import filter_listings, load_board
from settings import ROOT

TEMPLATES = ROOT / "templates"
STATIC = ROOT / "static"

env = Environment(
    loader=FileSystemLoader(str(TEMPLATES)),
    autoescape=select_autoescape(["html"]),
)


def _pull_when(pull: dict | None) -> str:
    if not pull or not pull.get("finished_at"):
        return "never"
    ts = pull["finished_at"]
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if ts.tzinfo:
        ts = ts.astimezone(timezone.utc)
    else:
        ts = ts.replace(tzinfo=timezone.utc)
    hour = ts.hour
    suffix = "p" if hour >= 12 else "a"
    hour12 = hour % 12 or 12
    minute = ts.minute
    clock = f"{hour12}:{minute:02d}{suffix}"
    return f"{ts.day} {ts.strftime('%b')} · {clock} utc"


def _issue() -> str:
    today = date.today()
    return f"{today.day} {today.strftime('%b').lower()} {today.year}"


def _chips(cities: list[str], view: str, city: str | None) -> list[dict]:
    chips = [
        {
            "label": "with prices",
            "href": "?view=priced",
            "on": view == "priced" and not city,
        },
        {
            "label": "all nights",
            "href": "?view=all",
            "on": view == "all" and not city,
        },
        {
            "label": "worth watching",
            "href": "?view=watch",
            "on": view == "watch" and not city,
        },
        {
            "label": "next 7 days",
            "href": "?view=week",
            "on": view == "week" and not city,
        },
    ]
    for name in cities:
        chips.append(
            {
                "label": name,
                "href": f"?city={quote(name)}",
                "on": city == name,
            }
        )
    return chips


def render_board(
    listings=None,
    meta=None,
    *,
    view: str = "priced",
    city: str | None = None,
    pull_href: str = "?pull=1",
    show_chips: bool = True,
) -> str:
    if listings is None or meta is None:
        listings, meta = load_board()
    view = (view or "priced").strip().lower()
    if view not in {"priced", "all", "week", "watch"}:
        view = "priced"
    city = (city or "").strip() or None
    visible = filter_listings(listings, view=view, city=city)
    css = (STATIC / "style.css").read_text()
    pull = meta.get("pull")
    template = env.get_template("board.html")
    chips = _chips(meta.get("cities") or [], view, city) if show_chips else []
    return template.render(
        css=css,
        listings=visible,
        meta=meta,
        chips=chips,
        shown=len(visible),
        view=view,
        city=city,
        pull_when=_pull_when(pull),
        pull_href=pull_href,
        issue=_issue(),
        setup=None,
    )


def render_setup(missing: list[str], db_ok: bool | None = None) -> str:
    css = (STATIC / "style.css").read_text()
    template = env.get_template("board.html")
    return template.render(
        css=css,
        listings=[],
        meta={"count": 0, "priced": 0, "watching": 0, "cities": []},
        chips=[],
        shown=0,
        view="priced",
        city=None,
        pull_when="never",
        pull_href="#",
        issue=_issue(),
        setup={"missing": missing, "db_ok": db_ok},
    )
