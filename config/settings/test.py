"""Test ayarları (pytest). Testler PostgreSQL üzerinde çalışır."""

import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-secret-key")
os.environ.setdefault("DATABASE_URL", "postgres://rapidquiz:rapidquiz@localhost:5432/rapidquiz")

from .base import *  # noqa: E402, F403

DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
DATABASES["default"]["CONN_MAX_AGE"] = 0  # noqa: F405
LOGGING = {"version": 1, "disable_existing_loggers": False}
