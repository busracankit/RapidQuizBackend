from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.leaderboard.models import LeaderboardEntry
from apps.leaderboard.services import rank_of

from . import serializers as s
from . import services
from .models import Category

SESSION_TOKEN_HEADER = "X-Session-Token"

token_param = OpenApiParameter(
    name=SESSION_TOKEN_HEADER,
    type=str,
    location=OpenApiParameter.HEADER,
    required=True,
    description="Oturum açılırken dönen `session_token`.",
)


def errors(*codes: int) -> dict:
    return {code: OpenApiResponse(s.ErrorSerializer) for code in codes}


def session_token(request) -> str | None:
    return request.headers.get(SESSION_TOKEN_HEADER)


class CategoryListView(APIView):
    throttle_scope = "read"

    @extend_schema(
        tags=["quiz"], summary="Aktif kategoriler", responses=s.CategorySerializer(many=True)
    )
    def get(self, request):
        categories = Category.objects.filter(is_active=True).order_by("order", "id")
        return Response(s.CategorySerializer(categories, many=True).data)


class SessionCreateView(APIView):
    throttle_scope = "session_create"

    @extend_schema(
        tags=["quiz"],
        summary="Quiz oturumu aç",
        description=(
            "Kategoriden rastgele 20 soru seçer ve ilk soruyu döner. İlk sorunun sayacı "
            "3-2-1 sayımı kadar sonra başlar (`starts_in_ms`)."
        ),
        request=s.SessionCreateSerializer,
        responses={201: s.SessionStartOutSerializer, **errors(400, 404, 409, 429)},
    )
    def post(self, request):
        data = s.SessionCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        started = services.start_session(
            data.validated_data["category"], data.validated_data["client_type"]
        )
        return Response(s.start_payload(started), status=status.HTTP_201_CREATED)


class SessionCurrentView(APIView):
    throttle_scope = "read"

    @extend_schema(
        tags=["quiz"],
        summary="O anki soru (yenileme/devam)",
        description=(
            "Süresi dolmuş sorular sunucuda 'süre doldu' olarak kapatılır; o anki soru "
            "kalan süresiyle döner. Oturum bittiyse `question` null'dur."
        ),
        parameters=[token_param],
        responses={200: s.SessionStateOutSerializer, **errors(403, 404, 410, 429)},
    )
    def get(self, request, session_id):
        state = services.get_current(session_id, session_token(request))
        return Response(s.state_payload(state))


class SessionAnswerView(APIView):
    throttle_scope = "answer"

    @extend_schema(
        tags=["quiz"],
        summary="Cevap gönder",
        description=(
            "Cevabı (süre dolduysa `choice_id: null`) değerlendirir; sonucu ve sonraki soruyu "
            "döner. Aynı soruya tekrar gönderim ilk sonucu döner."
        ),
        parameters=[token_param],
        request=s.AnswerSerializer,
        responses={200: s.AnswerOutSerializer, **errors(400, 403, 404, 409, 410, 429)},
    )
    def post(self, request, session_id):
        data = s.AnswerSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        result = services.submit_answer(
            session_id,
            session_token(request),
            data.validated_data["question_id"],
            data.validated_data["choice_id"],
        )
        return Response(s.answer_payload(result))


class SessionResultView(APIView):
    throttle_scope = "read"

    @extend_schema(
        tags=["quiz"],
        summary="Biten oturumun sonucu",
        parameters=[token_param],
        responses={200: s.ResultOutSerializer, **errors(403, 404, 409, 410, 429)},
    )
    def get(self, request, session_id):
        state = services.get_result(session_id, session_token(request))
        entry = LeaderboardEntry.objects.filter(session=state.session).first()
        rank = rank_of(entry) if entry else None
        return Response(s.result_payload(state, entry, rank))
