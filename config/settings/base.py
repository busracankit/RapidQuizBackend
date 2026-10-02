"""Tüm ortamlar için ortak ayarlar."""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env", overwrite=False)

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Üçüncü parti
    "rest_framework",
    "drf_spectacular",
    "drf_spectacular_sidecar",
    "corsheaders",
    # Proje
    "apps.quiz",
    "apps.leaderboard",
]

MIDDLEWARE = [
    "config.middleware.HealthCheckMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

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

DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "tr"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# --- CORS ---
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
CORS_ALLOW_HEADERS = (
    "accept",
    "content-type",
    "x-session-token",
)
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# --- DRF ---
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    # API'de cookie/CSRF yok; oturum X-Session-Token ile taşınır.
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "config.api.api_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {
        "session_create": env("THROTTLE_SESSION_CREATE", default="30/min"),
        "answer": env("THROTTLE_ANSWER", default="120/min"),
        "score": env("THROTTLE_SCORE", default="10/min"),
        "read": env("THROTTLE_READ", default="300/min"),
    },
    # İstemci IP'si için güvenilen proxy sayısı (X-Forwarded-For). Yerelde 0 = REMOTE_ADDR.
    "NUM_PROXIES": env.int("DRF_NUM_PROXIES", default=0),
}

# Throttle sayaçları. Varsayılan LocMem süreç başınadır (gunicorn worker sayısı kadar
# gevşer); çok instance'a çıkılırsa paylaşılan bir cache (ör. Redis) tanımlanmalı.
CACHES = {"default": env.cache("CACHE_URL", default="locmemcache://")}

SPECTACULAR_SETTINGS = {
    "TITLE": "Rapid Quiz API",
    "DESCRIPTION": "Web ve mobil istemciler için ortak Rapid Quiz REST API'si.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SWAGGER_UI_DIST": "SIDECAR",
    "SWAGGER_UI_FAVICON_HREF": "SIDECAR",
    "REDOC_DIST": "SIDECAR",
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": r"/api/v[0-9]+",
}

# --- Oyun kuralları ---
QUIZ_TIME_LIMIT_MS = env.int("QUIZ_TIME_LIMIT_MS", default=5000)
QUIZ_LATENCY_GRACE_MS = env.int("QUIZ_LATENCY_GRACE_MS", default=750)
QUIZ_QUESTIONS_PER_SESSION = env.int("QUIZ_QUESTIONS_PER_SESSION", default=20)
# Oturum başına zorluk dağılımı (kolay/orta/zor); toplamı QUIZ_QUESTIONS_PER_SESSION olmalı.
QUIZ_DIFFICULTY_MIX = {1: 8, 2: 8, 3: 4}
# Sunucu, istemcinin göstereceği bekleme kadar served_at'i ileri tarihler.
QUIZ_READY_COUNTDOWN_MS = env.int("QUIZ_READY_COUNTDOWN_MS", default=3000)
QUIZ_FEEDBACK_MS = env.int("QUIZ_FEEDBACK_MS", default=800)
QUIZ_SESSION_EXPIRE_MINUTES = env.int("QUIZ_SESSION_EXPIRE_MINUTES", default=30)
QUIZ_CLEANUP_DAYS = env.int("QUIZ_CLEANUP_DAYS", default=30)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
