import os

import streamlit as st
import streamlit.components.v1 as components

from board import render_board, render_setup
from db import ping
from ingest import last_pull_age_seconds, maybe_refresh, run
from queries import load_board
from settings import auto_pull, missing_setup

st.set_page_config(
    page_title="days out",
    layout="wide",
    initial_sidebar_state="collapsed",
)

for key in ("TICKETMASTER_API_KEY", "DATABASE_URL", "AUTO_PULL"):
    try:
        if key in st.secrets:
            os.environ.setdefault(key, str(st.secrets[key]))
    except Exception:
        break

st.markdown(
    """
    <style>
      #MainMenu, header, footer, [data-testid="stToolbar"],
      [data-testid="stDecoration"], [data-testid="stStatusWidget"] {
        visibility: hidden;
        height: 0;
      }
      .block-container {
        padding: 18px 24px 0 !important;
        max-width: 980px !important;
      }
      [data-testid="stAppViewContainer"] {
        background: #c9bda4;
      }
      iframe { background: #efe6d0; }
      div[data-testid="stPills"] button {
        font-family: "IBM Plex Mono", ui-monospace, monospace;
        font-size: 0.78rem;
        background: #efe6d0 !important;
        color: #1a140c !important;
        border: 1px solid #1a140c !important;
      }
      div[data-testid="stPills"] button[aria-checked="true"] {
        background: #1a140c !important;
        color: #efe6d0 !important;
      }
      .stButton button {
        font-family: "IBM Plex Mono", ui-monospace, monospace;
        background: #efe6d0;
        color: #1a140c;
        border: 1px solid #1a140c;
      }
    </style>
    """,
    unsafe_allow_html=True,
)


def _paint(html: str, rows: int = 8) -> None:
    height = 280 + max(rows, 4) * 98
    components.html(html, height=min(height, 14000), scrolling=True)


missing = missing_setup()
if missing:
    _paint(render_setup(missing), 6)
    st.stop()

if not ping():
    _paint(render_setup(["DATABASE_URL"], db_ok=False), 6)
    st.stop()

if auto_pull():
    age = last_pull_age_seconds()
    if age is None or age > 3 * 3600:
        with st.spinner("asking Ticketmaster…"):
            maybe_refresh()

listings, meta = load_board()
views = ["with prices", "all nights", "next 7 days"]
options = views + list(meta.get("cities") or [])

bar, action = st.columns([6, 1])
with bar:
    choice = st.pills(
        "filter",
        options,
        default="with prices",
        key="board_filter",
        label_visibility="collapsed",
    )
with action:
    if st.button("pull again"):
        with st.spinner("asking Ticketmaster…"):
            run(note="board")
        st.rerun()

choice = choice or "with prices"
if choice == "with prices":
    view, city = "priced", None
elif choice == "all nights":
    view, city = "all", None
elif choice == "next 7 days":
    view, city = "week", None
else:
    view, city = "all", choice

html = render_board(
    listings,
    meta,
    view=view,
    city=city,
    pull_href="",
    show_chips=False,
)
_paint(html, html.count('class="row"') or 8)
