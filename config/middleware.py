"""Proje geneli middleware'ler."""

from django.db import connection
from django.http import JsonResponse

HEALTH_PATH = "/api/v1/health/"


class HealthCheckMiddleware:
    """`/api/v1/health/` isteğini ALLOWED_HOSTS kontrolünden önce yanıtlar.

    DigitalOcean health check isteklerini konteyner IP'siyle gönderebilir; bu
    middleware MIDDLEWARE listesinin en başında durur, DB'ye `SELECT 1` atar.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == HEALTH_PATH and request.method in ("GET", "HEAD"):
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    cursor.fetchone()
            except Exception:  # noqa: BLE001
                return JsonResponse({"status": "error", "database": "unavailable"}, status=503)
            return JsonResponse({"status": "ok"})
        return self.get_response(request)
