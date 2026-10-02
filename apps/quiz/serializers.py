"""Quiz API'sinin istek/yanıt şemaları ve yanıt gövdesi üreticileri."""

from rest_framework import serializers

from . import services
from .models import Category, QuizSession, SessionQuestion

_dt = serializers.DateTimeField()


def iso(value):
    return _dt.to_representation(value) if value else None


# --------------------------------------------------------------------------- istekler


class SessionCreateSerializer(serializers.Serializer):
    category = serializers.SlugField(help_text="Kategori slug'ı, ör. `yapay-zeka`.")
    client_type = serializers.ChoiceField(
        choices=QuizSession.ClientType.choices, default=QuizSession.ClientType.WEB
    )


class AnswerSerializer(serializers.Serializer):
    question_id = serializers.IntegerField(help_text="Cevaplanan sorunun `id` değeri.")
    choice_id = serializers.IntegerField(
        min_value=1,
        max_value=4,
        allow_null=True,
        help_text="Seçilen şıkkın `id` değeri (1–4). Süre dolduysa `null`.",
    )


# --------------------------------------------------------------------------- yanıtlar


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("slug", "name", "description", "icon", "color", "order")


class CategoryBriefSerializer(serializers.Serializer):
    slug = serializers.SlugField()
    name = serializers.CharField()
    color = serializers.CharField()


class ChoiceOutSerializer(serializers.Serializer):
    id = serializers.IntegerField(help_text="Bu soruya ve oturuma özel şık kimliği (1–4).")
    text = serializers.CharField()


class QuestionOutSerializer(serializers.Serializer):
    index = serializers.IntegerField(help_text="Sorunun oturumdaki sırası (1–20).")
    id = serializers.IntegerField()
    text = serializers.CharField()
    difficulty = serializers.IntegerField(help_text="1 kolay, 2 orta, 3 zor.")
    choices = ChoiceOutSerializer(many=True)
    served_at = serializers.DateTimeField(
        help_text="Sayacın başladığı (başlayacağı) sunucu zamanı."
    )
    starts_in_ms = serializers.IntegerField(
        help_text="Sayaç başlayana kadar beklenecek süre (3-2-1 sayımı veya geri bildirim)."
    )
    remaining_ms = serializers.IntegerField(help_text="Sayaç başladıktan sonra kalan süre.")


class AnswerSummarySerializer(serializers.Serializer):
    index = serializers.IntegerField()
    is_correct = serializers.BooleanField()
    timed_out = serializers.BooleanField()
    points = serializers.IntegerField()
    response_ms = serializers.IntegerField()


class SessionStartOutSerializer(serializers.Serializer):
    session_id = serializers.UUIDField()
    session_token = serializers.CharField(help_text="Yalnızca bir kez döner; `X-Session-Token`.")
    category = CategoryBriefSerializer()
    total_questions = serializers.IntegerField()
    time_limit_ms = serializers.IntegerField()
    question = QuestionOutSerializer()


class AnswerOutSerializer(serializers.Serializer):
    is_correct = serializers.BooleanField()
    timed_out = serializers.BooleanField()
    correct_choice_id = serializers.IntegerField()
    selected_choice_id = serializers.IntegerField(allow_null=True)
    points = serializers.IntegerField()
    score = serializers.IntegerField()
    correct_count = serializers.IntegerField()
    answered_count = serializers.IntegerField()
    finished = serializers.BooleanField()
    next_question = QuestionOutSerializer(allow_null=True)


class SessionStateOutSerializer(serializers.Serializer):
    session_id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=QuizSession.Status.choices)
    category = CategoryBriefSerializer()
    total_questions = serializers.IntegerField()
    time_limit_ms = serializers.IntegerField()
    score = serializers.IntegerField()
    correct_count = serializers.IntegerField()
    answered_count = serializers.IntegerField()
    finished = serializers.BooleanField()
    question = QuestionOutSerializer(allow_null=True)
    answers = AnswerSummarySerializer(many=True)


class ResultOutSerializer(serializers.Serializer):
    session_id = serializers.UUIDField()
    category = CategoryBriefSerializer()
    score = serializers.IntegerField()
    max_score = serializers.IntegerField()
    correct_count = serializers.IntegerField()
    total_questions = serializers.IntegerField()
    total_time_ms = serializers.IntegerField()
    finished_at = serializers.DateTimeField()
    answers = AnswerSummarySerializer(many=True)
    score_saved = serializers.BooleanField()
    player_name = serializers.CharField(allow_null=True)
    rank = serializers.IntegerField(allow_null=True)


class ErrorDetailSerializer(serializers.Serializer):
    code = serializers.CharField()
    message = serializers.CharField()
    details = serializers.JSONField(required=False)


class ErrorSerializer(serializers.Serializer):
    error = ErrorDetailSerializer()


# --------------------------------------------------------------------------- gövde üreticiler


def category_brief(category: Category) -> dict:
    return {"slug": category.slug, "name": category.name, "color": category.color}


def question_payload(sq: SessionQuestion | None) -> dict | None:
    if sq is None:
        return None
    return {
        "index": sq.order,
        "id": sq.question_id,
        "text": sq.question.text,
        "difficulty": sq.question.difficulty,
        "choices": services.public_choices(sq),
        "served_at": iso(sq.served_at),
        "starts_in_ms": services.starts_in_ms(sq),
        "remaining_ms": services.remaining_ms(sq),
    }


def answer_summary(sq: SessionQuestion) -> dict:
    return {
        "index": sq.order,
        "is_correct": bool(sq.is_correct),
        "timed_out": sq.timed_out,
        "points": sq.points,
        "response_ms": sq.response_ms or 0,
    }


def start_payload(started: services.StartedSession) -> dict:
    s = started.session
    return {
        "session_id": str(s.id),
        "session_token": started.token,
        "category": category_brief(s.category),
        "total_questions": services.questions_per_session(),
        "time_limit_ms": services.time_limit_ms(),
        "question": question_payload(started.question),
    }


def answer_payload(result: services.AnswerResult) -> dict:
    sq, s = result.answered, result.session
    return {
        "is_correct": bool(sq.is_correct),
        "timed_out": sq.timed_out,
        "correct_choice_id": result.correct_choice_id,
        "selected_choice_id": services.selected_choice_key(sq),
        "points": sq.points,
        "score": s.score,
        "correct_count": s.correct_count,
        "answered_count": s.current_index,
        "finished": result.finished,
        "next_question": question_payload(result.next_question),
    }


def state_payload(state: services.SessionState) -> dict:
    s = state.session
    return {
        "session_id": str(s.id),
        "status": s.status,
        "category": category_brief(s.category),
        "total_questions": services.questions_per_session(),
        "time_limit_ms": services.time_limit_ms(),
        "score": s.score,
        "correct_count": s.correct_count,
        "answered_count": s.current_index,
        "finished": state.finished,
        "question": question_payload(state.question),
        "answers": [answer_summary(a) for a in state.answers],
    }


def result_payload(state: services.SessionState, entry=None, rank=None) -> dict:
    s = state.session
    total = services.questions_per_session()
    return {
        "session_id": str(s.id),
        "category": category_brief(s.category),
        "score": s.score,
        "max_score": total * (services.BASE_POINTS + services.MAX_SPEED_BONUS),
        "correct_count": s.correct_count,
        "total_questions": total,
        "total_time_ms": s.total_time_ms,
        "finished_at": iso(s.finished_at),
        "answers": [answer_summary(a) for a in state.answers],
        "score_saved": entry is not None,
        "player_name": entry.player_name if entry else None,
        "rank": rank,
    }
