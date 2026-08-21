from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from settings import ROOT, database_url

SCHEMA_PATH = ROOT / "schema.sql"


def connect() -> psycopg.Connection:
    url = database_url()
    if not url:
        raise RuntimeError("DATABASE_URL is empty")
    return psycopg.connect(url, row_factory=dict_row)


@contextmanager
def get_conn():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_schema(conn: psycopg.Connection | None = None) -> None:
    statements = [
        chunk.strip()
        for chunk in Path(SCHEMA_PATH).read_text().split(";")
        if chunk.strip()
    ]

    def apply(c: psycopg.Connection) -> None:
        for statement in statements:
            c.execute(statement)

    if conn is None:
        with get_conn() as c:
            apply(c)
        return
    apply(conn)


def ping() -> bool:
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False
