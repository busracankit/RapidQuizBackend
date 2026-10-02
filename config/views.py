from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    """Şema için. Gerçek istekleri MIDDLEWARE başındaki HealthCheckMiddleware yanıtlar."""

    throttle_classes = []

    @extend_schema(
        tags=["system"],
        summary="Sağlık kontrolü",
        responses=inline_serializer("Health", {"status": serializers.CharField()}),
    )
    def get(self, request):  # pragma: no cover - middleware önce yanıtlar
        return Response({"status": "ok"})
