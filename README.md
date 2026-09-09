# LetterMatch

Compare two public **Letterboxd** diaries side by side. Enter two usernames and
LetterMatch lists every film *both* people have logged, sorted alphabetically,
with the star rating each of them gave it.

- Dark, minimal UI (FastAPI + Jinja, one container)
- SQLite cache of scraped profiles — first comparison is slow, the rest are instant
- Films rated very differently by the two users (≥ 1.5 stars apart) are flagged

## Is it free?

Yes. Letterboxd has **no free public API**, so LetterMatch reads **public** profile
pages directly (`/{user}/films/`). One request per ~72 films; results are cached
for 24h by default.

Posters:

- **Without any key** — pulled from each film's Letterboxd social image. Works, but
  it's a square-ish crop rather than a true poster.
- **With a free [TMDB API key](https://www.themoviedb.org/settings/api)** — set
  `TMDB_API_KEY` and you get proper movie posters. Still 100% free.

Comments/reviews are intentionally **not** fetched (it would mean one request per
film and risk rate-limiting).

## Run with Docker

```bash
docker compose up --build
# http://localhost:8000
```

The SQLite cache lives in the `lettermatch-data` volume.

## Run locally

```bash
python -m venv .venv && . .venv/Scripts/activate   # or .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Configuration (env vars)

| Variable | Default | Meaning |
|---|---|---|
| `TMDB_API_KEY` | *(empty)* | Enable TMDB posters |
| `LETTERMATCH_USER_TTL` | `86400` | Cache lifetime per profile, seconds |
| `LETTERMATCH_DB` | `data/lettermatch.db` | SQLite path |
| `LETTERMATCH_PAGE_CONCURRENCY` | `5` | Parallel page fetches when scraping |

Use `?refresh=1` on a comparison URL (or the "Force refresh" link) to bypass the cache.

## Notes

Not affiliated with Letterboxd. Scrapes only public data; be considerate with the
refresh button. Private profiles return no films.
