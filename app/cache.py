"""SQLite cache for Letterboxd data.

Three tables:
  users        - one row per synced username, tracks when it was last fetched
  user_films   - (username, film_slug) -> rating (1..10, half-star units) or NULL
  films        - film_slug -> display name, year, poster url (shared across users)
"""

import os
import sqlite3
import time
from contextlib import contextmanager

from .config import DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    username    TEXT PRIMARY KEY,
    synced_at   REAL NOT NULL,
    film_count  INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS user_films (
    username   TEXT NOT NULL,
    film_slug  TEXT NOT NULL,
    rating     INTEGER,
    PRIMARY KEY (username, film_slug)
);
CREATE TABLE IF NOT EXISTS films (
    film_slug   TEXT PRIMARY KEY,
    name        TEXT,
    year        INTEGER,
    poster_url  TEXT,
    fetched_at  REAL
);
"""


def init_db() -> None:
    directory = os.path.dirname(DB_PATH)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with _connect() as conn:
        conn.executescript(_SCHEMA)


@contextmanager
def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# --- users -----------------------------------------------------------------

def get_user_sync(username: str):
    with _connect() as conn:
        row = conn.execute(
            "SELECT username, synced_at, film_count FROM users WHERE username = ?",
            (username.lower(),),
        ).fetchone()
        return dict(row) if row else None


def replace_user_films(username: str, films: dict[str, int | None]) -> None:
    """films: {slug: rating_or_none}. Replaces the whole set for that user."""
    username = username.lower()
    with _connect() as conn:
        conn.execute("DELETE FROM user_films WHERE username = ?", (username,))
        conn.executemany(
            "INSERT INTO user_films (username, film_slug, rating) VALUES (?, ?, ?)",
            [(username, slug, rating) for slug, rating in films.items()],
        )
        conn.execute(
            "INSERT INTO users (username, synced_at, film_count) VALUES (?, ?, ?) "
            "ON CONFLICT(username) DO UPDATE SET synced_at = excluded.synced_at, "
            "film_count = excluded.film_count",
            (username, time.time(), len(films)),
        )


def get_user_films(username: str) -> dict[str, int | None]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT film_slug, rating FROM user_films WHERE username = ?",
            (username.lower(),),
        ).fetchall()
        return {r["film_slug"]: r["rating"] for r in rows}


# --- films ---------------------------------------------------------------

def get_films(slugs: list[str]) -> dict[str, dict]:
    if not slugs:
        return {}
    with _connect() as conn:
        marks = ",".join("?" * len(slugs))
        rows = conn.execute(
            f"SELECT film_slug, name, year, poster_url FROM films "
            f"WHERE film_slug IN ({marks})",
            slugs,
        ).fetchall()
        return {r["film_slug"]: dict(r) for r in rows}


def upsert_film(slug: str, name: str | None, year: int | None,
                poster_url: str | None) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO films (film_slug, name, year, poster_url, fetched_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(film_slug) DO UPDATE SET "
            "name = COALESCE(excluded.name, films.name), "
            "year = COALESCE(excluded.year, films.year), "
            "poster_url = COALESCE(excluded.poster_url, films.poster_url), "
            "fetched_at = excluded.fetched_at",
            (slug, name, year, poster_url, time.time()),
        )
