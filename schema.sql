CREATE TABLE IF NOT EXISTS venues (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    city          TEXT,
    state_code    TEXT,
    country_code  TEXT,
    address       TEXT,
    postal_code   TEXT,
    timezone      TEXT,
    latitude      DOUBLE PRECISION,
    longitude     DOUBLE PRECISION,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS events (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    url           TEXT,
    attraction    TEXT,
    venue_id      TEXT REFERENCES venues (id),
    local_date    DATE,
    local_time    TIME,
    datetime_utc  TIMESTAMPTZ,
    status        TEXT,
    genre         TEXT,
    segment       TEXT,
    image_url     TEXT,
    currency      TEXT,
    price_min     NUMERIC(10, 2),
    price_max     NUMERIC(10, 2),
    priced_at     TIMESTAMPTZ,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS events_date_idx ON events (local_date);
CREATE INDEX IF NOT EXISTS events_venue_idx ON events (venue_id);
CREATE INDEX IF NOT EXISTS events_status_idx ON events (status);

CREATE TABLE IF NOT EXISTS price_snapshots (
    id            BIGSERIAL PRIMARY KEY,
    event_id      TEXT NOT NULL REFERENCES events (id) ON DELETE CASCADE,
    captured_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    currency      TEXT,
    min_price     NUMERIC(10, 2),
    max_price     NUMERIC(10, 2),
    range_type    TEXT
);

CREATE INDEX IF NOT EXISTS snapshots_event_time_idx
    ON price_snapshots (event_id, captured_at DESC);

CREATE TABLE IF NOT EXISTS pulls (
    id            BIGSERIAL PRIMARY KEY,
    started_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at   TIMESTAMPTZ,
    ok            BOOLEAN,
    events_seen   INTEGER DEFAULT 0,
    priced_count  INTEGER DEFAULT 0,
    note          TEXT
);
