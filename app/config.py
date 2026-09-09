import os

# Cache freshness for a user's film list, in seconds (default 24h).
USER_TTL = int(os.getenv("LETTERMATCH_USER_TTL", str(24 * 3600)))

# SQLite cache location.
DB_PATH = os.getenv("LETTERMATCH_DB", "data/lettermatch.db")

# Optional TMDB API key (v3). If set, posters are resolved via TMDB first,
# which is faster and more robust than scraping Letterboxd's ajax endpoint.
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "").strip()

# Politeness knobs for scraping letterboxd.com.
HTTP_TIMEOUT = float(os.getenv("LETTERMATCH_HTTP_TIMEOUT", "20"))
PAGE_CONCURRENCY = int(os.getenv("LETTERMATCH_PAGE_CONCURRENCY", "5"))
POSTER_CONCURRENCY = int(os.getenv("LETTERMATCH_POSTER_CONCURRENCY", "8"))

USER_AGENT = os.getenv(
    "LETTERMATCH_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
)
