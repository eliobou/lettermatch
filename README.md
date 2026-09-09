# LetterMatch

Compare two public **Letterboxd** diaries side by side. Enter two usernames and
LetterMatch lists every film *both* people have logged, sorted alphabetically,
with the star rating each of them gave it.

- Dark, minimal UI (FastAPI + Jinja, one container)
- SQLite cache of scraped profiles — first comparison is slow, the rest are instant
- Uncached comparisons show a live progress bar (SSE, "page N / M")
- Stats panel: each user's average, biggest gaps, who rated higher / lower / equal

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

letterboxd.com is behind Cloudflare. Requests use [`curl_cffi`](https://github.com/lexiforest/curl_cffi)
with a real-browser TLS fingerprint to avoid the "Just a moment..." challenge. If
comparisons start returning **502 "Cloudflare block"**, try another
`LETTERMATCH_IMPERSONATE` value; if nothing works from your IP you'd need a
challenge-solver (e.g. FlareSolverr) in front.

## Run with Docker

```bash
docker compose up --build
# http://localhost:8000
```

The SQLite cache and a rotated log file (`lettermatch.log`) live in the
`lettermatch-data` volume (next to the DB). The log keeps `/` and `/compare`
hits — dropping health checks, posters and static files — and adds one line per
comparison saying, per user, whether the film list was a **CACHE hit** or freshly
**SCRAPED**:

```
docker compose exec lettermatch tail -f /data/lettermatch.log
```

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
| `LETTERMATCH_PAGE_CONCURRENCY` | `4` | Process-wide ceiling on concurrent requests to letterboxd.com |
| `LETTERMATCH_REQUEST_DELAY` | `0` | Optional fixed pause (seconds) after each request |
| `LETTERMATCH_IMPERSONATE` | `chrome` | Browser fingerprint `curl_cffi` uses to pass Cloudflare (`chrome131`, `safari17_2`, …) |
| `LETTERMATCH_LOG_LEVEL` | `INFO` | Level for the file log |
| `LETTERMATCH_SSL_VERIFY` | `true` | See "Corporate proxy" below |

Both profiles of a comparison are scraped concurrently, but every request passes
through one shared gate, so raising/lowering `PAGE_CONCURRENCY` is the only knob
that changes the actual rate Letterboxd sees.

Use `?refresh=1` on a comparison URL (or the "Force refresh" link) to bypass the cache.

## Reverse proxy note (SSE)

The progress bar uses Server-Sent Events on `/compare/events`. The response
already sends `X-Accel-Buffering: no`, which Nginx / Nginx Proxy Manager respects.
If the bar never moves and jumps straight to the result, add `proxy_buffering off;`
to that proxy host's advanced config. If SSE is blocked entirely, the page falls
back to a plain blocking request automatically.

## Corporate proxy / TLS inspection

If the build fails with `CERTIFICATE_VERIFY_FAILED`, or comparisons return **502**
inside Docker, your network injects a self-signed root CA that the container
doesn't trust.

- The `Dockerfile` already passes `--trusted-host` to pip so the **build** works.
- For **runtime** requests to letterboxd.com / TMDB, either:
  - **Proper fix** — mount the CA and point Python at it:
    ```yaml
    volumes:
      - ./corp-ca.pem:/etc/ssl/certs/corp-ca.pem:ro
    environment:
      SSL_CERT_FILE: /etc/ssl/certs/corp-ca.pem
    ```
  - **Quick fix** — set `LETTERMATCH_SSL_VERIFY=false` (skips cert validation on
    outbound requests only).

## Notes

Not affiliated with Letterboxd. Scrapes only public data; be considerate with the
refresh button. Private profiles return no films.
