"""Business logic: sync a user (cache-aware) and build the comparison."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from . import cache
from .config import USER_TTL
from .letterboxd import scrape_user_films

_log = logging.getLogger("lettermatch")


class _Tracker:
    """Aggregates scrape progress across both users for the SSE stream."""

    def __init__(self, on_progress):
        self._cb = on_progress
        self.total = 0   # 0 until the first page of each scraped user is in
        self.done = 0

    def set_pages(self, n: int) -> None:
        self.total += n
        self._fire()

    def page_done(self) -> None:
        self.done += 1
        self._fire()

    def _fire(self) -> None:
        try:
            self._cb(self.done, self.total)
        except Exception:  # a broken listener must never break the scrape
            pass


def is_fresh(username: str) -> bool:
    meta = cache.get_user_sync(username.strip().lower())
    return bool(meta and (time.time() - meta["synced_at"] < USER_TTL))


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

    @property
    def combined(self) -> float | None:
        """Mean of the two ratings, in half-star units; None if not comparable."""
        if self.rating_a is None or self.rating_b is None:
            return None
        return (self.rating_a + self.rating_b) / 2


@dataclass
class Stats:
    compared: int          # shared films where BOTH gave a numeric rating
    not_compared: int      # shared films where at least one didn't rate
    better_a: int          # films A rated higher than B
    better_b: int
    equal: int
    avg_shared_a: float | None   # A's mean rating (stars) over `compared` films
    avg_shared_b: float | None
    avg_all_a: float | None      # A's mean rating over ALL A's rated films
    avg_all_b: float | None
    avg_gap: float | None        # mean |A - B| over `compared` films, in stars
    affinity: float | None       # Pearson r of the two rating series (-1..1)

    @property
    def taste_match(self) -> int | None:
        """Affinity mapped to a friendly 0-100% (r=0 -> 50%)."""
        if self.affinity is None:
            return None
        return round((self.affinity + 1) / 2 * 100)


@dataclass
class Comparison:
    user_a: str
    user_b: str
    rows: list[Row]
    total_a: int
    total_b: int
    synced_a: float
    synced_b: float
    stats: Stats

    @property
    def shared(self) -> int:
        return len(self.rows)


def _mean_stars(values: list[int]) -> float | None:
    return round(sum(values) / len(values) / 2, 2) if values else None


def _pearson(xs: list[int], ys: list[int]) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:      # one rater gave the same score to everything
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return round(sxy / (sxx ** 0.5 * syy ** 0.5), 3)


def _build_stats(rows: list[Row], films_a: dict[str, int | None],
                 films_b: dict[str, int | None]) -> Stats:
    pairs = [(r.rating_a, r.rating_b) for r in rows
             if r.rating_a is not None and r.rating_b is not None]
    return Stats(
        compared=len(pairs),
        not_compared=len(rows) - len(pairs),
        better_a=sum(1 for a, b in pairs if a > b),
        better_b=sum(1 for a, b in pairs if b > a),
        equal=sum(1 for a, b in pairs if a == b),
        avg_shared_a=_mean_stars([a for a, _ in pairs]),
        avg_shared_b=_mean_stars([b for _, b in pairs]),
        avg_all_a=_mean_stars([r for r in films_a.values() if r is not None]),
        avg_all_b=_mean_stars([r for r in films_b.values() if r is not None]),
        avg_gap=(round(sum(abs(a - b) for a, b in pairs) / len(pairs) / 2, 2)
                 if pairs else None),
        affinity=_pearson([a for a, _ in pairs], [b for _, b in pairs]),
    )


async def sync_user(username: str, force: bool = False,
                    tracker=None) -> tuple[dict[str, int | None], float]:
    username = username.strip().lower()
    meta = cache.get_user_sync(username)
    fresh = meta and (time.time() - meta["synced_at"] < USER_TTL)

    if fresh and not force:
        films = cache.get_user_films(username)
        age_min = int((time.time() - meta["synced_at"]) / 60)
        _log.info("sync %s: CACHE hit (%d films, %dm old)", username, len(films), age_min)
        return films, meta["synced_at"]

    reason = "forced refresh" if force else ("stale" if meta else "never synced")
    t0 = time.time()
    scraped = await scrape_user_films(username, tracker=tracker)
    films = {f.slug: f.rating for f in scraped}
    cache.replace_user_films(username, films)
    for f in scraped:
        cache.upsert_film(f.slug, f.name, f.year, None)
    _log.info("sync %s: SCRAPED %d films in %.1fs (%s)",
              username, len(films), time.time() - t0, reason)
    return films, time.time()


async def compare(user_a: str, user_b: str, force: bool = False,
                  on_progress=None) -> Comparison:
    user_a, user_b = user_a.strip().lower(), user_b.strip().lower()
    _log.info("compare a=%s b=%s force=%s", user_a, user_b, force)
    t0 = time.time()

    tracker = _Tracker(on_progress) if on_progress else None

    # Both users are synced concurrently; the process-wide request gate in
    # letterboxd.py keeps the total rate the same as doing them one after another.
    (films_a, synced_a), (films_b, synced_b) = await asyncio.gather(
        sync_user(user_a, force, tracker), sync_user(user_b, force, tracker)
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

    stats = _build_stats(rows, films_a, films_b)
    _log.info("compare a=%s b=%s -> %d shared, %d compared, done in %.1fs",
              user_a, user_b, len(rows), stats.compared, time.time() - t0)

    return Comparison(
        user_a=user_a,
        user_b=user_b,
        rows=rows,
        total_a=len(films_a),
        total_b=len(films_b),
        synced_a=synced_a,
        synced_b=synced_b,
        stats=stats,
    )
