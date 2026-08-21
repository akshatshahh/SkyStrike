from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from board import render_board, render_setup
from db import ping
from ingest import maybe_refresh, run
from queries import load_board
from settings import auto_pull, missing_setup

app = FastAPI(title="days out", docs_url=None, redoc_url=None)


@app.get("/health")
def health():
    return {"ok": True, "db": ping()}


@app.get("/", response_class=HTMLResponse)
def home(pull: int | None = None, view: str = "priced", city: str | None = None):
    missing = missing_setup()
    if missing:
        return HTMLResponse(render_setup(missing))
    if not ping():
        return HTMLResponse(render_setup(["DATABASE_URL"], db_ok=False), status_code=503)
    if pull == 1:
        run(note="board")
        return RedirectResponse("/?view=priced", status_code=303)
    if auto_pull():
        maybe_refresh()
    return HTMLResponse(render_board(view=view, city=city))


@app.get("/api/listings")
def listings():
    missing = missing_setup()
    if missing:
        return JSONResponse({"error": "missing " + ", ".join(missing)}, status_code=503)
    rows, meta = load_board()
    pull = meta.get("pull") or {}
    return {
        "count": meta["count"],
        "priced": meta["priced"],
        "listings": [
            {
                "id": r["id"],
                "name": r["headline"],
                "event": r["name"],
                "venue": r["venue_name"],
                "city": r["city"],
                "when": r["when"],
                "days_out": r["days"],
                "price_min": r["lo"],
                "price_max": r["hi"],
                "url": r["url"],
            }
            for r in rows
        ],
        "last_pull": str(pull.get("finished_at") or ""),
    }


@app.post("/api/pull")
def pull_now():
    missing = missing_setup()
    if missing:
        return JSONResponse({"error": "missing " + ", ".join(missing)}, status_code=503)
    return run(note="api")
