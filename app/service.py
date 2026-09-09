"""Business logic: sync a user (cache-aware) and build the comparison."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from . import cache
from .config import USER_TTL
from .letterboxd import scrape_user_films


@dataclass
class Row:
    slug: str
    name: str
    year: int | None
    rating_a: int | None
    rating_b: int | None

    @property
    def gap(self) -> int | None:
        if self.rating_a is None or self.rating_b is None:
            return None
        return abs(self.rating_a - self.rating_b)


@dataclass
class Comparison:
    user_a: str
    user_b: str
    rows: list[Row]
    total_a: int
    total_b: int
    synced_a: float
    synced_b: float

    @property
    def shared(self) -> int:
        return len(self.rows)


async def sync_user(username: str, force: bool = False) -> tuple[dict[str, int | None], float]:
    username = username.strip().lower()
    meta = cache.get_user_sync(username)
    fresh = meta and (time.time() - meta["synced_at"] < USER_TTL)

    if fresh and not force:
        return cache.get_user_films(username), meta["synced_at"]

    scraped = await scrape_user_films(username)
    films = {f.slug: f.rating for f in scraped}
    cache.replace_user_films(username, films)
    for f in scraped:
        cache.upsert_film(f.slug, f.name, f.year, None)
    return films, time.time()


async def compare(user_a: str, user_b: str, force: bool = False) -> Comparison:
    # Both users are synced concurrently; the process-wide request gate in
    # letterboxd.py keeps the total rate the same as doing them one after another.
    (films_a, synced_a), (films_b, synced_b) = await asyncio.gather(
        sync_user(user_a, force), sync_user(user_b, force)
    )

    shared_slugs = sorted(set(films_a) & set(films_b))
    meta = cache.get_films(shared_slugs)

    rows: list[Row] = []
    for slug in shared_slugs:
        info = meta.get(slug, {})
        rows.append(Row(
            slug=slug,
            name=info.get("name") or slug.replace("-", " ").title(),
            year=info.get("year"),
            rating_a=films_a[slug],
            rating_b=films_b[slug],
        ))
    rows.sort(key=lambda r: (r.name.lower(), r.year or 0))

    return Comparison(
        user_a=user_a.strip().lower(),
        user_b=user_b.strip().lower(),
        rows=rows,
        total_a=len(films_a),
        total_b=len(films_b),
        synced_a=synced_a,
        synced_b=synced_b,
    )
