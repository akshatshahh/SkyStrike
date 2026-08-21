import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env", override=True)


def tm_key() -> str:
    return (os.environ.get("TICKETMASTER_API_KEY") or "").strip()


def database_url() -> str:
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if "neon.tech" in url and "sslmode=" not in url:
        url += ("&" if "?" in url else "?") + "sslmode=require"
    return url


def auto_pull() -> bool:
    return (os.environ.get("AUTO_PULL") or "1").strip().lower() not in {"0", "false", "no"}


def missing_setup() -> list[str]:
    needed = []
    if not tm_key():
        needed.append("TICKETMASTER_API_KEY")
    if not database_url():
        needed.append("DATABASE_URL")
    return needed
