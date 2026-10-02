from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.quiz.exceptions import CategoryNotFound
from apps.quiz.models import Category
from apps.quiz.views import errors, session_token, token_param

from . import serializers as s
from . import services


class LeaderboardView(APIView):
    throttle_scope = "read"

    @extend_schema(
        tags=["leaderboard"],
        summary="Kategorinin Top 10 listesi",
        parameters=[
            OpenApiParameter("category", str, OpenApiParameter.QUERY, required=True),
        ],
        responses={200: s.LeaderboardOutSerializer, **errors(400, 404, 429)},
    )
    def get(self, request):
        query = s.LeaderboardQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        category = Category.objects.filter(
            slug=query.validated_data["category"], is_active=True
        ).first()
        if category is None:
            raise CategoryNotFound()
        return Response(s.leaderboard_payload(category, services.top_entries(category)))


class SessionScoreView(APIView):
    throttle_scope = "score"

    @extend_schema(
        tags=["leaderboard"],
        summary="Skoru isimle kaydet",
        description="Yalnızca tamamlanmış oturum için ve bir kez kaydedilebilir.",
        parameters=[token_param],
        request=s.ScoreSerializer,
        responses={201: s.ScoreOutSerializer, **errors(400, 403, 404, 409, 410, 429)},
    )
    def post(self, request, session_id):
        data = s.ScoreSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        saved = services.save_score(
            session_id, session_token(request), data.validated_data["player_name"]
        )
        category = saved.entry.category
        return Response(
            {
                "entry": s.entry_payload(saved.entry, saved.rank),
                "rank": saved.rank,
                "in_top": any(e.pk == saved.entry.pk for e in saved.top),
                "leaderboard": s.leaderboard_payload(category, saved.top),
            },
            status=status.HTTP_201_CREATED,
        )
