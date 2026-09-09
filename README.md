# LetterMatch

Compare two public [Letterboxd](https://letterboxd.com) accounts: every film both
users have logged, side by side, with each user's star rating.

## Features

- Side-by-side ratings for shared films, with star colours showing who rated higher
- Stats: a taste-match score, each user's average, average gap, who rated higher / lower / equal
- Sort by title, biggest rating gap, or combined rating
- Live progress bar while an uncached profile is being fetched
- Results are cached, so repeat comparisons are instant
- Dark, single-page UI; deploys as one container

## How it works

Letterboxd has no open API, so LetterMatch reads the public `/{user}/films/`
pages directly (one request per ~72 films). Those pages are behind Cloudflare, so
requests use [`curl_cffi`](https://github.com/lexiforest/curl_cffi) with a
real-browser TLS fingerprint.

Each user's film list and ratings are stored in a local SQLite file and reused
until they go stale (24h by default). A comparison is then just a set
intersection plus some arithmetic — no network calls once both users are cached.

Posters come from TMDB if an API key is set, otherwise from each film's Letterboxd
social image. Reviews are not fetched (it would mean one request per film).

Backend is FastAPI + Jinja templates, server-rendered. Uncached comparisons show
a progress page that streams scrape progress over SSE, then loads the result.

## Deploy

```bash
git clone https://github.com/<you>/lettermatch.git
cd lettermatch
cp .env.example .env          # optional: add a TMDB API key for real posters
docker compose up -d --build
```

Open <http://localhost:8000>.

The SQLite cache and a rotating log file are written to `./data`.

## Configuration

Set via environment (see `docker-compose.yml`):

| Variable | Default | Description |
|---|---|---|
| `TMDB_API_KEY` | *(empty)* | Free [TMDB v3 key](https://www.themoviedb.org/settings/api) for proper posters. Without it, posters use Letterboxd's social images. |
| `LETTERMATCH_USER_TTL` | `86400` | How long (seconds) a cached profile is reused before re-scraping. |
| `LETTERMATCH_PAGE_CONCURRENCY` | `4` | Max concurrent requests to letterboxd.com (shared across a comparison). |
| `LETTERMATCH_REQUEST_DELAY` | `0` | Fixed pause (seconds) after each request, if you want to go slower. |
| `LETTERMATCH_IMPERSONATE` | `chrome` | Browser fingerprint used to pass Cloudflare (`chrome131`, `safari17_2`, …). |
| `LETTERMATCH_SSL_VERIFY` | `true` | Set to `false` only if a TLS-inspecting proxy breaks outbound HTTPS. |
| `LETTERMATCH_LOG_LEVEL` | `INFO` | Level for the file log. |
| `LETTERMATCH_DB` | `/data/lettermatch.db` | SQLite path (log file sits next to it). |

Add `?refresh=1` to a comparison URL to bypass the cache for that request.

## Behind a reverse proxy

Forward to the container's port `8000`. The progress bar uses SSE; the response
already sends `X-Accel-Buffering: no`, but if your proxy still buffers, add
`proxy_buffering off;` for this host. If SSE is unavailable the page falls back to
a plain blocking request.

## Local development

```bash
python -m venv .venv
. .venv/bin/activate            # .venv\Scripts\activate on Windows
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Endpoints

| Route | Purpose |
|---|---|
| `GET /` | Username form |
| `GET /compare?a=&b=` | Comparison (progress page first if uncached; `&refresh=1`, `&direct=1`) |
| `GET /compare/events?a=&b=` | SSE scrape-progress stream |
| `GET /poster/{slug}` | Poster redirect (resolved once, then cached) |
| `GET /healthz` | Health check |

## Limitations

- Public profiles only.
- Scraping depends on Letterboxd's HTML; selectors may need updating if the site changes.
- If Cloudflare hard-blocks your server's IP, try another `LETTERMATCH_IMPERSONATE`
  value or run a challenge solver in front.
- Not affiliated with Letterboxd or TMDB.
