# days out

Upcoming Ticketmaster Discovery listings, sorted by how many days until the show. Each pull stores the printed low / high in Postgres so you can see if it moved.

This is not StubHub and not a seat map. A lot of events come back with no `priceRanges`. The board leaves those blank.

**watch** is just a flag:
- the low fell since last pull
- the high is at least 2.5× the low
- three days out or less, and they actually sent a number

Rooms and names are in `watchlist.py`.

## local

Consumer key: [developer.ticketmaster.com](https://developer.ticketmaster.com)

Postgres: `docker compose up -d` (port **5433** so it doesn’t fight another local Postgres), or a Neon URI.

```bash
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python ingest.py
streamlit run streamlit_app.py
```

Same page via FastAPI: `uvicorn web:app --reload`

## streamlit cloud

Repo file is `streamlit_app.py`. Secrets:

```toml
TICKETMASTER_API_KEY = "..."
DATABASE_URL = "postgresql://..."
```

Use Neon (or any hosted Postgres). Don’t commit `.env`. First load will ingest if the last good pull is older than three hours.

## schema

`venues`, `events`, `price_snapshots`, `pulls` — created on first connect. Discovery quota is 5 req/s, 5k/day.
