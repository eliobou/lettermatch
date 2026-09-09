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

# TLS verification for outbound requests. Set to "false" only if you are behind a
# TLS-inspecting proxy and cannot mount its root CA (see SSL_CERT_FILE in README).
SSL_VERIFY = os.getenv("LETTERMATCH_SSL_VERIFY", "true").lower() not in {"false", "0", "no"}
# Process-wide ceiling on concurrent requests to letterboxd.com (shared across
# both users of a comparison) and an optional fixed pause after each request.
PAGE_CONCURRENCY = int(os.getenv("LETTERMATCH_PAGE_CONCURRENCY", "4"))
REQUEST_DELAY = float(os.getenv("LETTERMATCH_REQUEST_DELAY", "0"))

USER_AGENT = os.getenv(
    "LETTERMATCH_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
)

# Browser profile curl_cffi impersonates to get past Cloudflare on letterboxd.com.
# Try "chrome124", "chrome131", "safari17_2", etc. if the default is challenged.
IMPERSONATE = os.getenv("LETTERMATCH_IMPERSONATE", "chrome")
