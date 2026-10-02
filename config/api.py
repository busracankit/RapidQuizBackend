"""API genel altyapısı: sabit hata formatı ve JSON 404."""

import logging

from django.http import JsonResponse
from rest_framework import exceptions as drf_exc
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from apps.quiz.exceptions import QuizError

logger = logging.getLogger(__name__)

_CODES = {
    drf_exc.ValidationError: ("validation_error", "İstek geçersiz."),
    drf_exc.ParseError: ("invalid_json", "İstek gövdesi geçerli bir JSON değil."),
    drf_exc.NotFound: ("not_found", "Bulunamadı."),
    drf_exc.MethodNotAllowed: ("method_not_allowed", "Bu metot desteklenmiyor."),
    drf_exc.UnsupportedMediaType: (
        "unsupported_media_type",
        "İçerik türü application/json olmalı.",
    ),
    drf_exc.NotAcceptable: ("not_acceptable", "İstenen yanıt biçimi desteklenmiyor."),
    drf_exc.PermissionDenied: ("permission_denied", "Bu işlem için yetkiniz yok."),
}


def error_body(code: str, message: str, details=None) -> dict:
    body = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    return body


def api_exception_handler(exc, context):
    """Tüm API hatalarını `{"error": {"code", "message"[, "details"]}}` biçimine çevirir."""
    if isinstance(exc, QuizError):
        return Response(error_body(exc.code, exc.message), status=exc.status_code)

    response = drf_exception_handler(exc, context)
    if response is None:
        logger.exception("Beklenmeyen API hatası", exc_info=exc)
        return Response(error_body("server_error", "Beklenmeyen bir hata oluştu."), status=500)

    if isinstance(exc, drf_exc.Throttled):
        wait = int(exc.wait or 0)
        response.data = error_body(
            "rate_limited", f"Çok fazla istek. {wait} saniye sonra tekrar deneyin."
        )
        return response

    for cls, (code, message) in _CODES.items():
        if isinstance(exc, cls):
            details = response.data if isinstance(exc, drf_exc.ValidationError) else None
            response.data = error_body(code, message, details)
            return response

    response.data = error_body(getattr(exc, "default_code", "error"), str(exc))
    return response


def api_not_found(request, exception=None):
    """`/api/` altındaki bilinmeyen adresler için JSON 404; diğerleri için Django'nun sayfası."""
    if request.path.startswith("/api/"):
        return JsonResponse(error_body("not_found", "Bulunamadı."), status=404)
    from django.views.defaults import page_not_found

    return page_not_found(request, exception)
