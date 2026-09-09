from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

import httpx
from fastapi import FastAPI, Query, Request
from fastapi.responses import (
    HTMLResponse, RedirectResponse, Response, StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import cache, logs, tmdb
from .config import TMDB_API_KEY
from .letterboxd import LetterboxdBlocked, ProfileNotFound, resolve_poster_url
from .service import compare, is_fresh

_log = logging.getLogger("lettermatch")
BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="LetterMatch")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# Slugs we tried and failed to resolve a poster for; retried after an hour.
_POSTER_MISS: dict[str, float] = {}
_TRANSPARENT_GIF = bytes.fromhex(
    "47494638396101000100800000000000ffffff21f90401000000002c"
    "00000000010001000002024401003b"
)


@app.on_event("startup")
def _startup() -> None:
    logs.setup_logging()
    cache.init_db()


def stars(rating: int | None) -> dict:
    """rating is in half-star units (1..10)."""
    if not rating:
        return {"full": 0, "half": False, "empty": 5, "text": "—"}
    full = rating // 2
    half = bool(rating % 2)
    return {
        "full": full,
        "half": half,
        "empty": 5 - full - (1 if half else 0),
        "text": f"{rating / 2:g}",
    }


templates.env.filters["stars"] = stars
templates.env.filters["ago"] = lambda ts: _ago(ts)


def _ago(ts: float) -> str:
    if not ts:
        return "never"
    delta = int(time.time() - ts)
    if delta < 90:
        return "just now"
    if delta < 3600:
        return f"{delta // 60} min ago"
    if delta < 86400:
        return f"{delta // 3600} h ago"
    return f"{delta // 86400} d ago"


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


def _err_page(request: Request, e: Exception):
    if isinstance(e, ProfileNotFound):
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "error": f"Letterboxd profile not found: “{e}”"},
            status_code=404,
        )
    return templates.TemplateResponse(
        "index.html",
        {"request": request,
         "error": "Couldn't reach Letterboxd (network error or Cloudflare block). "
                  f"Try again in a moment. [{type(e).__name__}]"},
        status_code=502,
    )


@app.get("/compare", response_class=HTMLResponse)
async def compare_view(
    request: Request,
    a: str = Query(..., min_length=1, max_length=40),
    b: str = Query(..., min_length=1, max_length=40),
    refresh: int = Query(0),
    direct: int = Query(0),
):
    cached = is_fresh(a) and is_fresh(b) and not refresh

    # Slow path: nothing usable in cache -> show the progress page, which streams
    # /compare/events and reloads here (warm) when done. `direct=1` forces the
    # old blocking behaviour (fallback if EventSource fails).
    if not cached and not direct:
        return templates.TemplateResponse(
            "loading.html",
            {"request": request, "a": a.strip().lower(), "b": b.strip().lower(),
             "refresh": refresh},
        )

    try:
        result = await compare(a, b, force=bool(refresh))
    except (ProfileNotFound, httpx.HTTPError, LetterboxdBlocked) as e:
        _log.warning("compare a=%s b=%s: failed (%s: %s)", a, b, type(e).__name__, e)
        return _err_page(request, e)
    return templates.TemplateResponse(
        "compare.html", {"request": request, "c": result}
    )


@app.get("/compare/events")
async def compare_events(
    a: str = Query(..., min_length=1, max_length=40),
    b: str = Query(..., min_length=1, max_length=40),
    refresh: int = Query(0),
):
    """SSE stream: progress events while scraping, then `done` or `error`."""
    queue: asyncio.Queue = asyncio.Queue()

    def on_progress(done: int, total: int) -> None:
        queue.put_nowait(("progress", {"done": done, "total": total}))

    async def worker() -> None:
        try:
            await compare(a, b, force=bool(refresh), on_progress=on_progress)
            queue.put_nowait(("done", {}))
        except ProfileNotFound as e:
            queue.put_nowait(("error", {"message": f"Profil Letterboxd introuvable : « {e} »"}))
        except (httpx.HTTPError, LetterboxdBlocked) as e:
            _log.warning("events a=%s b=%s: %s: %s", a, b, type(e).__name__, e)
            queue.put_nowait(("error", {"message": "Letterboxd injoignable (erreur réseau ou blocage Cloudflare)."}))
        except Exception:  # noqa: BLE001
            _log.exception("events a=%s b=%s: unexpected", a, b)
            queue.put_nowait(("error", {"message": "Erreur interne."}))

    async def stream():
        yield ": connected\n\n"
        task = asyncio.create_task(worker())
        try:
            while True:
                try:
                    kind, data = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                yield f"event: {kind}\ndata: {json.dumps(data)}\n\n"
                if kind in ("done", "error"):
                    return
        finally:
            task.cancel()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                 "Connection": "keep-alive"},
    )


def _blank_poster() -> Response:
    return Response(_TRANSPARENT_GIF, media_type="image/gif",
                    headers={"Cache-Control": "public, max-age=3600"})


@app.get("/poster/{slug}")
async def poster(slug: str):
    """Resolve a film's poster URL (cached in SQLite) and redirect to the CDN."""
    slug = slug[:120]
    info = cache.get_films([slug]).get(slug, {})

    url = info.get("poster_url")
    if not url:
        if time.time() - _POSTER_MISS.get(slug, 0) < 3600:
            return _blank_poster()
        try:
            if TMDB_API_KEY:
                url = await tmdb.resolve_poster_url(info.get("name") or slug,
                                                   info.get("year"))
            if not url:
                url = await resolve_poster_url(slug)
        except httpx.HTTPError:
            url = None
        if not url:
            _POSTER_MISS[slug] = time.time()
            return _blank_poster()
        cache.upsert_film(slug, info.get("name"), info.get("year"), url)

    return RedirectResponse(url, status_code=307,
                            headers={"Cache-Control": "public, max-age=604800"})


@app.get("/healthz")
def healthz():
    return {"ok": True}
