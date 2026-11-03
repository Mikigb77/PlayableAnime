"""Django settings. Every value comes from the environment through `lucid.env.Env`."""

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

from lucid.env import BACKEND_DIR, LOCAL_DATABASE_URL, Env, split_csv

ENV = Env()

DEBUG = ENV.debug
SECRET_KEY = ENV.django_secret_key or ("insecure-dev-key" if DEBUG else "")
if not SECRET_KEY:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY is required when DEBUG is off.")
# Fail at startup, not on the first query: /health never touches the database, so a deploy with a
# missing database secret would otherwise look healthy.
DATABASE_URL = ENV.database_url or (LOCAL_DATABASE_URL if DEBUG else "")
if not DATABASE_URL:
    raise ImproperlyConfigured("DATABASE_URL is required when DEBUG is off.")

ALLOWED_HOSTS = split_csv(ENV.allowed_hosts)
CSRF_TRUSTED_ORIGINS = split_csv(ENV.csrf_trusted_origins)
# Cloud Run terminates TLS and forwards the original scheme.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "servestatic",
    "corsheaders",
    "accounts",
    "stories",
    "media",
]

MIDDLEWARE = [
    # First, so every log line of the request, including errors below, carries its ids (T4).
    "lucid.middleware.RequestContextMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "servestatic.middleware.ServeStaticMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Last, so the error responses it rewrites still get the headers added above.
    "lucid.middleware.ErrorEnvelopeMiddleware",
]

ROOT_URLCONF = "lucid.urls"
ASGI_APPLICATION = "lucid.asgi.application"

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


def _database(url: str) -> dict:
    """Neon behind PgBouncer in transaction mode (B2): no persistent connections, and no
    server-side cursors, which don't survive across pooled transactions."""
    config = dj_database_url.parse(url, conn_max_age=0)
    config["DISABLE_SERVER_SIDE_CURSORS"] = True
    return config


DATABASES = {"default": _database(DATABASE_URL)}
if ENV.database_url_unpooled:
    # Neon's direct URL, for `manage.py migrate --database direct` (B2). Same database, so the
    # test runner mirrors it instead of creating a second one.
    DATABASES["direct"] = _database(ENV.database_url_unpooled) | {"TEST": {"MIRROR": "default"}}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
        "OPTIONS": {"user_attributes": ("email", "display_name")},
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# The admin's CSS and JS, collected into the image and served by ServeStatic.
STATIC_URL = "static/"
STATIC_ROOT = BACKEND_DIR / "staticfiles"

CORS_ALLOW_ALL_ORIGINS = split_csv(ENV.cors_origins) == ["*"]
CORS_ALLOWED_ORIGINS = [] if CORS_ALLOW_ALL_ORIGINS else split_csv(ENV.cors_origins)
CORS_ALLOW_HEADERS = [
    "accept",
    "authorization",
    "content-type",
    "x-llm-api-key",
    "x-llm-provider",
    "x-request-id",
]
CORS_EXPOSE_HEADERS = ["x-request-id"]

# The API's own settings, read through `django.conf.settings`.
LLM_PROVIDER = ENV.llm_provider
GCP_PROJECT = ENV.gcp_project
VERTEX_LOCATION = ENV.vertex_location
NARRATOR_MODEL = ENV.narrator_model

# Sign-in (T8, K7, F8); see accounts/.
GOOGLE_OAUTH_CLIENT_IDS = split_csv(ENV.google_oauth_client_ids)
OWNER_EMAILS = [email.lower() for email in split_csv(ENV.owner_emails)]
MIN_SIGNUP_AGE = ENV.min_signup_age
TRUSTED_PROXY_HOPS = ENV.trusted_proxy_hops
# Pictures (M4): a private Cloud Storage bucket in production, local files otherwise.
MEDIA_BUCKET = ENV.media_bucket
PICTURE_ROOT = ENV.picture_root or BACKEND_DIR / "media-local"
PICTURE_URL_TTL_S = ENV.picture_url_ttl_s
if not DEBUG and LLM_PROVIDER == "vertex" and not MEDIA_BUCKET:
    # A real deployment would keep pictures on one instance's ephemeral disk, where other
    # instances can't serve them and a restart loses them.
    raise ImproperlyConfigured("MEDIA_BUCKET is required when LLM_PROVIDER is vertex.")

# JSON lines on stdout, which Cloud Run sends to Cloud Logging (T4 to T6, B3).
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"json": {"()": "lucid.logs.JsonFormatter", "project": GCP_PROJECT}},
    "handlers": {
        "stdout": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "json",
        }
    },
    "root": {"handlers": ["stdout"], "level": ENV.log_level},
    "loggers": {
        # Django and uvicorn log through the same JSON handler.
        "django": {"handlers": ["stdout"], "level": ENV.log_level, "propagate": False},
        # 4xx responses are already in our request line; keep Django's line only for 5xx.
        "django.request": {"level": "ERROR"},
        "uvicorn": {"handlers": ["stdout"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"level": "INFO"},
        # Our own request line replaces uvicorn's plain-text access log.
        "uvicorn.access": {"handlers": [], "level": "WARNING", "propagate": False},
    },
}
