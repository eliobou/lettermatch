"""Optional TMDB poster resolver, used first when TMDB_API_KEY is set.

A free TMDB API key (v3 auth) is enough: https://www.themoviedb.org/settings/api
"""

from __future__ import annotations

import httpx

from .config import HTTP_TIMEOUT, TMDB_API_KEY, USER_AGENT

_SEARCH = "https://api.themoviedb.org/3/search/movie"
_IMG_BASE = "https://image.tmdb.org/t/p/w342"


async def resolve_poster_url(name: str, year: int | None) -> str | None:
    if not TMDB_API_KEY or not name:
        return None
    params = {"api_key": TMDB_API_KEY, "query": name, "include_adult": "true"}
    if year:
        params["year"] = str(year)
    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT}, timeout=HTTP_TIMEOUT, follow_redirects=True
    ) as client:
        r = await client.get(_SEARCH, params=params)
        if r.status_code != 200:
            return None
        results = r.json().get("results") or []
        path = next((x.get("poster_path") for x in results if x.get("poster_path")), None)
        return f"{_IMG_BASE}{path}" if path else None
