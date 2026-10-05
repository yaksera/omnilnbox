"""
Django settings for the OmniInbox backend.

Everything environment-specific is read from environment variables so the same
code runs locally (SQLite) and in production (Postgres behind Docker).
"""
import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def env(key, default=None):
    return os.environ.get(key, default)


def env_bool(key, default=False):
    return str(os.environ.get(key, default)).lower() in {"1", "true", "yes", "on"}


def env_list(key, default=""):
    return [v.strip() for v in os.environ.get(key, default).split(",") if v.strip()]


# Load a local .env file if present (tiny loader, no extra dependency)
_env_file = BASE_DIR / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

DEBUG = env_bool("DJANGO_DEBUG", False)  # secure by default; .env sets true for local dev
_INSECURE_KEYS = {"", "dev-insecure-change-me", "change-me-to-a-long-random-string"}
SECRET_KEY = env("DJANGO_SECRET_KEY", "")
if SECRET_KEY in _INSECURE_KEYS and not DEBUG:
    raise ImproperlyConfigured("Set DJANGO_SECRET_KEY to a long random value when DJANGO_DEBUG is false.")
# Never silently change an existing key: without FIELD_ENCRYPTION_KEY, stored channel
# credentials are encrypted with a key derived from SECRET_KEY.
SECRET_KEY = SECRET_KEY or "dev-insecure-change-me"

# Public URL where this backend is reachable from the internet (used to build webhook URLs)
PUBLIC_BASE_URL = env("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
# Where the Next.js app lives (used for OAuth redirects back to the UI)
FRONTEND_URL = env("FRONTEND_URL", "http://localhost:3000").rstrip("/")
# Key used to encrypt channel credentials at rest (Fernet, urlsafe base64 32 bytes).
FIELD_ENCRYPTION_KEY = env("FIELD_ENCRYPTION_KEY", "")
if not FIELD_ENCRYPTION_KEY and not DEBUG:
    raise ImproperlyConfigured("Set FIELD_ENCRYPTION_KEY (Fernet key) when DJANGO_DEBUG is false.")
# How often the worker polls email / polling-mode channels (seconds)
POLL_INTERVAL_SECONDS = int(env("POLL_INTERVAL_SECONDS", "30"))
# Allow IMAP/SMTP hosts on private networks (only for self-hosted/dev; blocks SSRF in SaaS mode)
ALLOW_PRIVATE_HOSTS = env_bool("ALLOW_PRIVATE_HOSTS", False)
# Admin site path (don't expose the default /admin/ on a public URL)
ADMIN_URL = env("ADMIN_URL", "admin/").strip("/") + "/"

# Hosts: explicit list; the public webhook host and local dev hosts are always allowed.
_public_host = urlparse(PUBLIC_BASE_URL).hostname
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
if _public_host and "*" not in ALLOWED_HOSTS and _public_host not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(_public_host)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "core",
    "integrations",
    "inbox",
    "billing",
    "publishing",
    "automations",
    "accounts",
    "commerce",
    "broadcasts",
    "developers",
    "affiliates",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}", conn_max_age=600
    )
}
if DATABASES["default"]["ENGINE"].endswith("sqlite3"):
    # The server, the worker and background automations write at the same time: take the write lock up front
    # (no "database is locked" from lock upgrades) and wait for it instead of failing straight away.
    DATABASES["default"].setdefault("OPTIONS", {}).update({"transaction_mode": "IMMEDIATE", "timeout": 20})

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Cache: rate limits and instant updates (core.realtime). With more than one server process (gunicorn workers,
# the background worker) set REDIS_URL so they all share it; without it each process has its own memory cache.
REDIS_URL = env("REDIS_URL", "")
if REDIS_URL:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": REDIS_URL}}

REST_FRAMEWORK = {
    # Proxies in front of Django that append the client IP to X-Forwarded-For (nginx/Caddy/Cloudflare -> Next.js -> Django).
    # Used by rate limits to find the visitor's real IP. 0 = ignore X-Forwarded-For (use the socket address).
    "NUM_PROXIES": int(env("TRUSTED_PROXIES", "1")),
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "developers.auth.ApiKeyAuthentication",  # "Bearer omni_…" API keys (checked first)
        "accounts.auth.RevocableJWTAuthentication",  # JWT + "log out of all devices"
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 50,
    # Rate limits: brute-force protection on auth + a generous per-user ceiling
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "user": env("THROTTLE_USER", "1200/min"),
        "auth": env("THROTTLE_AUTH", "20/min"),
        "send": env("THROTTLE_SEND", "60/min"),
        "ai": env("THROTTLE_AI", "30/min"),
        "widget": env("THROTTLE_WIDGET", "60/min"),
        "widget_site": env("THROTTLE_WIDGET_SITE", "600/min"),
        "affiliate": env("THROTTLE_AFFILIATE", "60/min"),
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(env("JWT_ACCESS_MINUTES", "60"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(env("JWT_REFRESH_DAYS", "14"))),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,  # a stolen, already-used refresh token stops working
    "UPDATE_LAST_LOGIN": True,
}

CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
CORS_ALLOW_HEADERS = [
    "accept", "authorization", "content-type", "origin", "x-workspace-id",
]
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", "http://localhost:3000")

# --- Payments (leave a key empty to hide that payment method) ---
KHALTI_SECRET_KEY = env("KHALTI_SECRET_KEY", "")
KHALTI_BASE_URL = env("KHALTI_BASE_URL", "https://dev.khalti.com/api/v2").rstrip("/")  # prod: https://khalti.com/api/v2
ESEWA_PRODUCT_CODE = env("ESEWA_PRODUCT_CODE", "EPAYTEST" if DEBUG else "")
ESEWA_SECRET_KEY = env("ESEWA_SECRET_KEY", "8gBm/:&EnhH.1/q" if DEBUG else "")  # public sandbox key
ESEWA_FORM_URL = env("ESEWA_FORM_URL", "https://rc-epay.esewa.com.np/api/epay/main/v2/form")
ESEWA_STATUS_URL = env("ESEWA_STATUS_URL", "https://uat.esewa.com.np/api/epay/transaction/status/")
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET", "")

# One-click "Connect with Facebook" (WhatsApp Embedded Signup + Pages/Instagram). See integrations/meta_connect.py
META_APP_ID = env("META_APP_ID", "")
META_APP_SECRET = env("META_APP_SECRET", "")
META_VERIFY_TOKEN = env("META_VERIFY_TOKEN", "")
META_WA_CONFIG_ID = env("META_WA_CONFIG_ID", "")
META_PAGES_CONFIG_ID = env("META_PAGES_CONFIG_ID", "")
# Optional: a separate Facebook Login for Business configuration for Publish (posting). Falls back to the Pages one.
META_PUBLISH_CONFIG_ID = env("META_PUBLISH_CONFIG_ID", "")

# --- Social publishing ---
# Google Cloud OAuth client (YouTube Data API v3). Redirect URI: <PUBLIC_BASE_URL>/api/publishing/oauth/youtube/callback/
# AI (OpenRouter: one API key for GPT-4o, Claude, Gemini, ...). Model ids: https://openrouter.ai/models
OPENROUTER_API_KEY = env("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = env("OPENROUTER_MODEL") or "openai/gpt-4o"
OPENROUTER_BASE_URL = (env("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1").rstrip("/")
# Only for the cost estimate on the platform admin dashboard (blended input+output price of your model, USD per 1M tokens).
# gpt-4o is about $2.50 in / $10 out; most chat traffic is input, so ~$4 is a fair blend. Check openrouter.ai/models.
AI_COST_PER_MILLION_TOKENS_USD = env("AI_COST_PER_MILLION_TOKENS_USD", "4")
# Knowledge base search by meaning (embeddings through the same OpenRouter key). Off = keyword search only.
EMBEDDINGS_ENABLED = env_bool("EMBEDDINGS_ENABLED", True)
EMBEDDING_MODEL = env("EMBEDDING_MODEL", "openai/text-embedding-3-small")
# Voice notes and photos (payment screenshots) are read by a model that understands audio and images.
# Gemini Flash handles Nepali speech well and is cheap; any OpenRouter model with audio/image input works.
AI_AUDIO_MODEL = env("AI_AUDIO_MODEL", "google/gemini-2.5-flash")
AI_VISION_MODEL = env("AI_VISION_MODEL", "google/gemini-2.5-flash")
# Test runs: no network calls for embeddings, and document/website imports run immediately (not in a thread)
import sys as _sys  # noqa: E402
if len(_sys.argv) > 1 and _sys.argv[1] == "test":
    EMBEDDINGS_ENABLED = False
    KNOWLEDGE_IMPORT_SYNC = True
    BACKGROUND_SYNC = True  # courier auto-booking etc. run inline
GOOGLE_CLIENT_ID = env("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = env("GOOGLE_CLIENT_SECRET", "")
# TikTok developer app (Login Kit + Content Posting API). Redirect URI: <PUBLIC_BASE_URL>/api/publishing/oauth/tiktok/callback/
TIKTOK_CLIENT_KEY = env("TIKTOK_CLIENT_KEY", "")
TIKTOK_CLIENT_SECRET = env("TIKTOK_CLIENT_SECRET", "")
# Uploaded media (never served statically; only via signed, expiring links)
MEDIA_ROOT = Path(env("MEDIA_ROOT") or BASE_DIR / "media")
MEDIA_URL = "/media-not-public/"
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
ATTACHMENT_MAX_MB = int(env("ATTACHMENT_MAX_MB", "25"))  # photos / files / voice notes in conversations

# --- Email (invites). Leave EMAIL_HOST empty to show invite links in the UI instead. ---
EMAIL_HOST = env("EMAIL_HOST", "")
EMAIL_PORT = int(env("EMAIL_PORT", "587"))
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "OmniInbox <no-reply@omniinbox.app>")
if not EMAIL_HOST:
    # No SMTP yet: password-reset / verification emails are printed in the backend terminal instead.
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
# Contact address sent to browser push services (Web Push / VAPID)
PUSH_CONTACT_EMAIL = env("PUSH_CONTACT_EMAIL", "") or DEFAULT_FROM_EMAIL.split("<")[-1].rstrip(">").strip()

# Request size limits (webhook payloads, API bodies)
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

# Security headers (always on) + HTTPS-only cookies/HSTS in production
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
    SECURE_REDIRECT_EXEMPT = [r"^health/$"]
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(env("SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
}

# --- Affiliate program ---
# Recurring commission on every payment from a referred workspace, for as long as it stays subscribed.
AFFILIATE_COMMISSION_RATE = env("AFFILIATE_COMMISSION_RATE", "0.20")  # 20%; override per affiliate in Admin
AFFILIATE_HOLD_DAYS = int(env("AFFILIATE_HOLD_DAYS", "14"))  # refund window before a commission can be paid out
AFFILIATE_MIN_PAYOUT = {"NPR": int(env("AFFILIATE_MIN_PAYOUT_NPR", "2000")), "USD": int(env("AFFILIATE_MIN_PAYOUT_USD", "15"))}
