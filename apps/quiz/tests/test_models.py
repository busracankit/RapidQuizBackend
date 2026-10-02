import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.conftest import make_question, make_session
from apps.quiz.models import Category, Choice, Question, QuizSession, SessionQuestion

pytestmark = pytest.mark.django_db


class TestCategory:
    def test_seed_creates_five_categories_in_order(self):
        slugs = list(Category.objects.values_list("slug", flat=True))
        assert slugs == ["yazilim", "yapay-zeka", "bilgisayar-muhendisligi", "ulkeler", "fizik"]

    def test_seed_colors_match_design_guide(self):
        colors = dict(Category.objects.values_list("slug", "color"))
        assert colors == {
            "yazilim": "#3B82F6",
            "yapay-zeka": "#A855F7",
            "bilgisayar-muhendisligi": "#F97316",
            "ulkeler": "#10B981",
            "fizik": "#06B6D4",
        }

    @pytest.mark.parametrize("color", ["3B82F6", "#3B82F", "#GGGGGG", "blue"])
    def test_invalid_hex_color_rejected(self, color):
        cat = Category(name="Test", slug="test", color=color)
        with pytest.raises(ValidationError) as exc:
            cat.full_clean()
        assert "color" in exc.value.message_dict

    def test_slug_is_unique(self):
        with pytest.raises(IntegrityError):
            Category.objects.create(name="Kopya", slug="yazilim", color="#000000")

    def test_category_with_questions_cannot_be_deleted(self, question):
        from django.db.models import ProtectedError

        with pytest.raises(ProtectedError):
            question.category.delete()


class TestQuestion:
    def test_text_max_length_is_120(self, category):
        q = Question(category=category, text="x" * 121)
        with pytest.raises(ValidationError) as exc:
            q.full_clean()
        assert "text" in exc.value.message_dict

    def test_difficulty_check_constraint(self, category):
        with pytest.raises(IntegrityError):
            Question.objects.create(category=category, text="Zor mu?", difficulty=4)

    def test_active_queryset(self, category):
        make_question(category, text="Aktif")
        make_question(category, text="Pasif", is_active=False)
        assert list(Question.objects.active().values_list("text", flat=True)) == ["Aktif"]


class TestChoice:
    def test_text_max_length_is_40(self, question):
        c = Choice(question=question, text="x" * 41)
        with pytest.raises(ValidationError):
            c.full_clean()

    def test_only_one_correct_choice_per_question(self, question):
        with pytest.raises(IntegrityError):
            Choice.objects.create(question=question, text="ikinci doğru", is_correct=True)

    def test_many_wrong_choices_allowed(self, question):
        Choice.objects.create(question=question, text="beşinci", is_correct=False)
        assert question.choices.filter(is_correct=False).count() == 4

    def test_choices_cascade_with_question(self, question):
        question.delete()
        assert Choice.objects.count() == 0


class TestQuizSession:
    def test_token_is_stored_hashed(self, category):
        token, token_hash = QuizSession.generate_token()
        assert token.startswith("tok_")
        assert token not in token_hash
        assert len(token_hash) == 64

        session = QuizSession.objects.create(category=category, token_hash=token_hash)
        assert session.check_token(token)
        assert not session.check_token(token + "x")
        assert not session.check_token(None)
        assert not session.check_token("")

    def test_tokens_are_unique(self):
        tokens = {QuizSession.generate_token()[0] for _ in range(100)}
        assert len(tokens) == 100

    def test_defaults(self, quiz_session):
        assert quiz_session.status == QuizSession.Status.IN_PROGRESS
        assert quiz_session.current_index == 0
        assert quiz_session.score == 0
        assert quiz_session.client_type == QuizSession.ClientType.WEB
        assert quiz_session.started_at is not None
        assert quiz_session.finished_at is None

    def test_current_index_cannot_exceed_20(self, quiz_session):
        quiz_session.current_index = 21
        with pytest.raises(IntegrityError):
            quiz_session.save()

    def test_token_hash_unique(self, category, quiz_session):
        with pytest.raises(IntegrityError):
            QuizSession.objects.create(category=category, token_hash=quiz_session.token_hash)


class TestSessionQuestion:
    def test_order_unique_per_session(self, category, quiz_session):
        q1 = make_question(category, text="S1")
        q2 = make_question(category, text="S2")
        SessionQuestion.objects.create(session=quiz_session, question=q1, order=1)
        with pytest.raises(IntegrityError):
            SessionQuestion.objects.create(session=quiz_session, question=q2, order=1)

    def test_question_once_per_session(self, category, quiz_session):
        q1 = make_question(category, text="S1")
        SessionQuestion.objects.create(session=quiz_session, question=q1, order=1)
        with pytest.raises(IntegrityError):
            SessionQuestion.objects.create(session=quiz_session, question=q1, order=2)

    @pytest.mark.parametrize("order", [0, 21])
    def test_order_range(self, quiz_session, question, order):
        with pytest.raises(IntegrityError):
            SessionQuestion.objects.create(session=quiz_session, question=question, order=order)

    def test_same_question_in_different_sessions(self, category, question):
        s1, s2 = make_session(category), make_session(category)
        SessionQuestion.objects.create(session=s1, question=question, order=1)
        SessionQuestion.objects.create(session=s2, question=question, order=1)
        assert SessionQuestion.objects.count() == 2

    def test_played_question_cannot_be_deleted(self, quiz_session, question):
        from django.db.models import ProtectedError

        SessionQuestion.objects.create(session=quiz_session, question=question, order=1)
        with pytest.raises(ProtectedError):
            question.delete()

    def test_choice_order_json_and_answer_fields(self, quiz_session, question):
        ids = list(question.choices.values_list("id", flat=True))[::-1]
        sq = SessionQuestion.objects.create(
            session=quiz_session, question=question, order=1, choice_order=ids
        )
        sq.refresh_from_db()
        assert sq.choice_order == ids
        assert sq.is_correct is None
        assert sq.timed_out is False
        assert sq.is_answered is False

    def test_session_delete_cascades(self, quiz_session, question):
        SessionQuestion.objects.create(session=quiz_session, question=question, order=1)
        with transaction.atomic():
            quiz_session.delete()
        assert SessionQuestion.objects.count() == 0
