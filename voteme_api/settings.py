import os
import ssl
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR / "venv" / ".env")

SECRET_KEY = os.environ.get("SECRET_KEY", "insecure-dev-key")
DEBUG = os.environ.get("DEBUG", "True").lower() == "true"

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt",
    "accounts",
    "organizations",
    "competitions",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "organizations.middleware.TenantMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "voteme_api.urls"

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

WSGI_APPLICATION = "voteme_api.wsgi.application"

required_db_vars = ("DB_NAME", "DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT")
missing_db_vars = [var for var in required_db_vars if not os.environ.get(var)]
if missing_db_vars:
    raise ValueError(
        f"Missing database env vars: {', '.join(missing_db_vars)}. "
        "Set them in BackEnd/venv/.env"
    )

def _mysql_ssl_context() -> ssl.SSLContext:
    """Aiven MySQL uses TLS; allow connection without local CA bundle in dev."""
    context = ssl.create_default_context()
    if os.environ.get("DB_SSL_VERIFY", "false").lower() != "true":
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    return context


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.environ["DB_NAME"],
        "USER": os.environ["DB_USER"],
        "PASSWORD": os.environ["DB_PASSWORD"],
        "HOST": os.environ["DB_HOST"],
        "PORT": os.environ["DB_PORT"],
        # Aiven free tiers have low connection limits; avoid pooling in dev.
        "CONN_MAX_AGE": int(os.environ.get("DB_CONN_MAX_AGE", "0")),
        "OPTIONS": {
            "charset": "utf8mb4",
            "ssl": _mysql_ssl_context(),
        },
    },
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "organizations.authentication.TenantJWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=12),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
}

CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]

# Invitation-only by default; enable when onboarding a paid client at /signup
PUBLIC_SIGNUP_ENABLED = os.environ.get("PUBLIC_SIGNUP_ENABLED", "false").lower() == "true"
SIGNUP_SECRET_CODE = os.environ.get("SIGNUP_SECRET_CODE", "")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "voteme-default",
    }
}

# TikTok Login Kit + Display API
TIKTOK_CLIENT_KEY = os.environ.get("TIKTOK_CLIENT_KEY", "")
TIKTOK_CLIENT_SECRET = os.environ.get("TIKTOK_CLIENT_SECRET", "")
TIKTOK_REDIRECT_URI = os.environ.get(
    "TIKTOK_REDIRECT_URI",
    "http://localhost:3000/dashboard/tiktok/callback",
)
# desktop = http://localhost + PKCE (hex SHA256). web = https redirect, no PKCE.
_tiktok_login_kit = os.environ.get("TIKTOK_LOGIN_KIT", "").strip().lower()
if _tiktok_login_kit in ("desktop", "web"):
    TIKTOK_LOGIN_KIT = _tiktok_login_kit
elif TIKTOK_REDIRECT_URI.lower().startswith("http://"):
    TIKTOK_LOGIN_KIT = "desktop"
else:
    TIKTOK_LOGIN_KIT = "web"
TIKTOK_SCOPES = os.environ.get("TIKTOK_SCOPES", "user.info.basic,video.list")

# Brand mention keyword for comment scoring (case-insensitive)
BRAND_MENTION_KEYWORD = os.environ.get("BRAND_MENTION_KEYWORD", "ellaresort")

# Optional TikTok Research API (academic) for comment text ingestion
TIKTOK_RESEARCH_CLIENT_KEY = os.environ.get("TIKTOK_RESEARCH_CLIENT_KEY", "")
TIKTOK_RESEARCH_CLIENT_SECRET = os.environ.get("TIKTOK_RESEARCH_CLIENT_SECRET", "")
