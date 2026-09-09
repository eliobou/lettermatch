"""Scraping helpers for public Letterboxd profiles.

We only hit the paginated films grid (`/{user}/films/page/{n}/`), which gives us
everything we need in one request per 72 films:

  * film slug, display name and year   (data-item-slug / data-item-name)
  * the user's rating in half-star units 1..10   (span.rating.rated-N)

letterboxd.com sits behind Cloudflare, so requests go through `curl_cffi` with a
real-browser TLS/HTTP fingerprint (`impersonate=`); a plain HTTP client gets the
"Just a moment..." challenge page instead.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

from curl_cffi.requests import AsyncSession
from selectolax.parser import HTMLParser

from .config import (
    HTTP_TIMEOUT, IMPERSONATE, PAGE_CONCURRENCY, REQUEST_DELAY, SSL_VERIFY,
)

BASE = "https://letterboxd.com"
_NAME_YEAR = re.compile(r"^(.*?)\s*\((\d{4})\)\s*$")
_RATED = re.compile(r"rated-(\d+)")

# One global gate for every outbound letterboxd.com request in the process, so
# comparing two users in parallel does NOT raise the total request rate — it
# just interleaves their pages under the same ceiling.
_GATE = asyncio.Semaphore(PAGE_CONCURRENCY)

_BROWSER_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
              "image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Upgrade-Insecure-Requests": "1",
}


class ProfileNotFound(Exception):
    pass


class LetterboxdBlocked(Exception):
    """Network failure, or a Cloudflare challenge instead of the real page."""


@dataclass
class ScrapedFilm:
    slug: str
    name: str
    year: int | None
    rating: int | None  # half-star units, 1..10


def _session() -> AsyncSession:
    return AsyncSession(
        impersonate=IMPERSONATE,
        timeout=HTTP_TIMEOUT,
        verify=SSL_VERIFY,
        allow_redirects=True,
        headers=_BROWSER_HEADERS,
    )


async def _get(session: AsyncSession, url: str):
    async with _GATE:
        try:
            r = await session.get(url)
        except Exception as e:  # curl_cffi raises its own error hierarchy
            raise LetterboxdBlocked(f"request to {url} failed: {e}") from e
        if REQUEST_DELAY:
            await asyncio.sleep(REQUEST_DELAY)
    if r.status_code in (403, 429, 503) and "just a moment" in r.text[:2000].lower():
        raise LetterboxdBlocked(
            f"Cloudflare challenge on {url} (HTTP {r.status_code})"
        )
    return r


def _parse_page(html: str) -> list[ScrapedFilm]:
    tree = HTMLParser(html)
    films: list[ScrapedFilm] = []
    for li in tree.css("li.griditem"):
        comp = li.css_first("div.react-component[data-item-slug]")
        if comp is None:
            continue
        slug = comp.attributes.get("data-item-slug")
        if not slug:
            continue
        raw_name = (comp.attributes.get("data-item-name")
                    or comp.attributes.get("data-item-full-display-name") or slug)
        name, year = raw_name, None
        m = _NAME_YEAR.match(raw_name)
        if m:
            name, year = m.group(1).strip(), int(m.group(2))

        rating = None
        rating_node = li.css_first("span.rating")
        if rating_node is not None:
            rm = _RATED.search(rating_node.attributes.get("class", ""))
            if rm:
                rating = int(rm.group(1))

        films.append(ScrapedFilm(slug=slug, name=name, year=year, rating=rating))
    return films


def _last_page(html: str) -> int:
    tree = HTMLParser(html)
    pages = [
        int(a.text()) for a in tree.css("div.paginate-pages li a")
        if a.text().strip().isdigit()
    ]
    return max(pages) if pages else 1


async def scrape_user_films(username: str) -> list[ScrapedFilm]:
    """Return every film on the user's public profile.

    Raises ProfileNotFound (404) or LetterboxdBlocked (network / Cloudflare).
    """
    username = username.strip().lower()
    async with _session() as session:
        first = await _get(session, f"{BASE}/{username}/films/page/1/")
        if first.status_code == 404:
            raise ProfileNotFound(username)
        if first.status_code >= 400:
            raise LetterboxdBlocked(f"HTTP {first.status_code} for {username}")

        films = _parse_page(first.text)
        last = _last_page(first.text)

        if last > 1:
            async def fetch(page: int) -> list[ScrapedFilm]:
                r = await _get(session, f"{BASE}/{username}/films/page/{page}/")
                if r.status_code >= 400:
                    raise LetterboxdBlocked(f"HTTP {r.status_code} page {page}")
                return _parse_page(r.text)

            results = await asyncio.gather(*(fetch(p) for p in range(2, last + 1)))
            for chunk in results:
                films.extend(chunk)

    # De-duplicate by slug, keeping the rated occurrence if any.
    seen: dict[str, ScrapedFilm] = {}
    for f in films:
        if f.slug not in seen or (seen[f.slug].rating is None and f.rating is not None):
            seen[f.slug] = f
    return list(seen.values())


_OG_IMAGE = re.compile(
    r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']'
)


async def resolve_poster_url(slug: str) -> str | None:
    """Scrape the film page for its og:image (hosted on Letterboxd's CDN).

    Used only as a fallback when no TMDB key is configured. The image is a
    social-card crop, not a true poster, but it hotlinks without a referer check.
    """
    try:
        async with _session() as session:
            r = await _get(session, f"{BASE}/film/{slug}/")
    except LetterboxdBlocked:
        return None
    if r.status_code != 200:
        return None
    m = _OG_IMAGE.search(r.text)
    return m.group(1) if m else None
