from datetime import UTC, datetime, timedelta

import pytest

from apps.conftest import fill_category, make_question
from apps.quiz import exceptions as exc
from apps.quiz import services
from apps.quiz.models import Category, QuizSession, SessionQuestion

pytestmark = pytest.mark.django_db

T0 = datetime(2026, 10, 1, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def clock(time_machine):
    time_machine.move_to(T0, tick=False)
    return time_machine


@pytest.fixture
def started(full_category, clock):
    return services.start_session(full_category.slug, "web")


def current(started):
    return started.session.session_questions.get(order=started.session.current_index + 1)


def key_of(sq, correct=True):
    sq = SessionQuestion.objects.select_related("question").get(pk=sq.pk)
    right = services.correct_choice_id(sq)
    return right if correct else (right % 4) + 1


def answer(started, *, after_ms, correct=True, choice=..., clock=None):
    """Sayacın başlamasından `after_ms` sonra o anki soruyu cevaplar."""
    s = QuizSession.objects.get(pk=started.session.pk)
    sq = s.session_questions.get(order=s.current_index + 1)
    clock.move_to(sq.served_at + timedelta(milliseconds=after_ms), tick=False)
    if choice is ...:
        choice = key_of(sq, correct)
    return services.submit_answer(s.id, started.token, sq.question_id, choice)


# --------------------------------------------------------------------------- puan


@pytest.mark.parametrize(
    ("is_correct", "response_ms", "points"),
    [
        (True, 500, 145),
        (True, 1800, 132),
        (True, 4900, 101),
        (True, 0, 150),
        (True, 5000, 100),
        (True, 9000, 100),
        (True, -50, 150),
        (False, 300, 0),
    ],
)
def test_calculate_points(is_correct, response_ms, points):
    assert services.calculate_points(is_correct, response_ms) == points


# --------------------------------------------------------------------------- soru seçimi


class TestPickQuestions:
    def test_twenty_unique_questions_with_difficulty_mix(self, full_category):
        ids = services.pick_question_ids(full_category)
        assert len(ids) == len(set(ids)) == 20
        from apps.quiz.models import Question

        diffs = list(Question.objects.filter(id__in=ids).values_list("difficulty", flat=True))
        assert (diffs.count(1), diffs.count(2), diffs.count(3)) == (8, 8, 4)

    def test_shortage_in_one_difficulty_is_filled_from_others(self, category):
        fill_category(category, easy=12, medium=7, hard=1)
        assert len(set(services.pick_question_ids(category))) == 20

    def test_not_enough_questions(self, category):
        fill_category(category, easy=10, medium=9, hard=0)
        with pytest.raises(exc.NotEnoughQuestions):
            services.pick_question_ids(category)

    def test_skips_inactive_and_malformed_questions(self, category):
        fill_category(category, easy=10, medium=9, hard=0)
        make_question(category, text="pasif", is_active=False)
        broken = make_question(category, text="3 şıklı")
        broken.choices.last().delete()
        no_correct = make_question(category, text="doğrusuz")
        no_correct.choices.update(is_correct=False)
        with pytest.raises(exc.NotEnoughQuestions):
            services.pick_question_ids(category)


# --------------------------------------------------------------------------- oturum açma


class TestStartSession:
    def test_creates_session_with_twenty_questions(self, started):
        session = started.session
        assert session.status == QuizSession.Status.IN_PROGRESS
        assert session.session_questions.count() == 20
        assert started.token.startswith("tok_")
        assert session.check_token(started.token)
        assert started.token not in session.token_hash

    def test_first_question_timer_starts_after_ready_countdown(self, started):
        assert started.question.order == 1
        assert started.question.served_at == T0 + timedelta(milliseconds=3000)
        assert not started.session.session_questions.filter(
            order__gt=1, served_at__isnull=False
        ).exists()

    def test_choice_order_is_permutation_of_question_choices(self, started):
        for sq in started.session.session_questions.select_related("question"):
            assert sorted(sq.choice_order) == sorted(
                sq.question.choices.values_list("id", flat=True)
            )

    def test_public_choices_hide_db_ids_and_correctness(self, started):
        choices = services.public_choices(started.question)
        assert [c["id"] for c in choices] == [1, 2, 3, 4]
        assert all(set(c) == {"id", "text"} for c in choices)

    def test_client_type_saved(self, full_category, clock):
        s = services.start_session(full_category.slug, "ios")
        assert s.session.client_type == "ios"

    @pytest.mark.parametrize("slug", ["yok", ""])
    def test_unknown_category(self, slug):
        with pytest.raises(exc.CategoryNotFound):
            services.start_session(slug)

    def test_inactive_category(self, full_category):
        Category.objects.filter(pk=full_category.pk).update(is_active=False)
        with pytest.raises(exc.CategoryNotFound):
            services.start_session(full_category.slug)

    def test_sessions_get_different_question_orders(self, full_category, clock):
        orders = {
            tuple(
                services.start_session(full_category.slug)
                .session.session_questions.order_by("order")
                .values_list("question_id", flat=True)
            )
            for _ in range(5)
        }
        assert len(orders) > 1


# --------------------------------------------------------------------------- cevap


class TestSubmitAnswer:
    def test_correct_answer_scores_and_serves_next(self, started, clock):
        result = answer(started, after_ms=1800, clock=clock)
        sq = result.answered
        assert sq.is_correct and not sq.timed_out
        assert sq.response_ms == 1800 and sq.points == 132
        assert result.session.score == 132 and result.session.correct_count == 1
        assert result.correct_choice_id == key_of(sq)
        assert result.next_question.order == 2
        # Sonraki sorunun sayacı 0,8 sn geri bildirimden sonra başlar.
        answered_at = sq.served_at + timedelta(milliseconds=1800)
        assert result.next_question.served_at == answered_at + timedelta(milliseconds=800)
        assert not result.finished

    def test_wrong_answer(self, started, clock):
        result = answer(started, after_ms=900, correct=False, clock=clock)
        assert result.answered.is_correct is False
        assert result.answered.points == 0
        assert result.answered.response_ms == 900
        assert result.session.score == 0
        assert result.correct_choice_id != result.answered.selected_choice_id

    def test_client_timeout_with_null_choice(self, started, clock):
        result = answer(started, after_ms=5020, choice=None, clock=clock)
        sq = result.answered
        assert sq.timed_out and sq.is_correct is False
        assert sq.response_ms == 5000 and sq.points == 0
        assert sq.selected_choice_id is None

    def test_answer_within_latency_grace_counts(self, started, clock):
        result = answer(started, after_ms=5600, clock=clock)
        assert result.answered.is_correct and not result.answered.timed_out
        assert result.answered.response_ms == 5000
        assert result.answered.points == 100

    def test_answer_after_grace_is_timed_out(self, started, clock):
        result = answer(started, after_ms=5751, clock=clock)
        assert result.answered.timed_out
        assert result.answered.points == 0
        assert result.session.score == 0

    def test_answer_before_timer_start_counts_as_zero_ms(self, started, clock):
        result = answer(started, after_ms=-500, clock=clock)
        assert result.answered.response_ms == 0
        assert result.answered.points == 150

    def test_second_answer_returns_first_result(self, started, clock):
        first = answer(started, after_ms=1000, clock=clock)
        sq = first.answered
        clock.shift(timedelta(milliseconds=100))
        again = services.submit_answer(
            started.session.id, started.token, sq.question_id, key_of(sq, correct=False)
        )
        assert again.answered.pk == sq.pk
        assert again.answered.is_correct is True
        assert again.session.score == first.session.score
        assert again.session.current_index == 1
        assert again.next_question.pk == first.next_question.pk

    def test_question_mismatch_for_future_question(self, started, clock):
        future = started.session.session_questions.get(order=3)
        with pytest.raises(exc.QuestionMismatch):
            services.submit_answer(started.session.id, started.token, future.question_id, 1)

    def test_question_mismatch_for_foreign_question(self, started, category):
        foreign = make_question(category, text="Oturumda olmayan soru")
        with pytest.raises(exc.QuestionMismatch):
            services.submit_answer(started.session.id, started.token, foreign.id, 1)

    @pytest.mark.parametrize("choice", [0, 5, -1, "1", True, 1.0])
    def test_invalid_choice(self, started, clock, choice):
        with pytest.raises(exc.InvalidChoice):
            answer(started, after_ms=1000, choice=choice, clock=clock)
        assert QuizSession.objects.get(pk=started.session.pk).current_index == 0

    def test_wrong_token(self, started):
        with pytest.raises(exc.InvalidSessionToken):
            services.submit_answer(
                started.session.id, "tok_yanlis", started.question.question_id, 1
            )
        with pytest.raises(exc.InvalidSessionToken):
            services.submit_answer(started.session.id, None, started.question.question_id, 1)

    @pytest.mark.parametrize("session_id", ["00000000-0000-0000-0000-000000000000", "uuid-degil"])
    def test_unknown_session(self, session_id):
        with pytest.raises(exc.SessionNotFound):
            services.submit_answer(session_id, "tok_x", 1, 1)


class TestFullGame:
    def test_twenty_answers_complete_the_session(self, started, clock):
        for i in range(20):
            result = answer(started, after_ms=1000, correct=(i % 2 == 0), clock=clock)
        session = result.session
        assert result.finished and result.next_question is None
        assert session.status == QuizSession.Status.COMPLETED
        assert session.current_index == 20
        assert session.correct_count == 10
        assert session.score == 10 * 140
        assert session.total_time_ms == 20 * 1000
        assert session.finished_at is not None

    def test_perfect_game_max_is_3000(self, started, clock):
        for _ in range(20):
            result = answer(started, after_ms=0, clock=clock)
        assert result.session.score == 3000

    def test_answer_after_finish_replays_last_or_rejects(self, started, clock):
        for _ in range(20):
            last = answer(started, after_ms=1000, clock=clock)
        replay = services.submit_answer(
            started.session.id, started.token, last.answered.question_id, 1
        )
        assert replay.answered.pk == last.answered.pk
        assert replay.session.score == last.session.score


# --------------------------------------------------------------------------- yenileme / devam


class TestResume:
    def test_current_returns_same_question_with_running_clock(self, started, clock):
        clock.move_to(T0 + timedelta(milliseconds=4000), tick=False)
        state = services.get_current(started.session.id, started.token)
        assert state.question.pk == started.question.pk
        assert services.starts_in_ms(state.question) == 0
        assert services.remaining_ms(state.question) == 4000  # 3 sn sayım + 1 sn geçti

    def test_starts_in_during_ready_countdown(self, started):
        assert services.starts_in_ms(started.question) == 3000
        assert services.remaining_ms(started.question) == 5000

    def test_overdue_question_is_timed_out_and_next_served(self, started, clock):
        served = started.question.served_at
        clock.move_to(served + timedelta(milliseconds=5751), tick=False)
        state = services.get_current(started.session.id, started.token)
        first = SessionQuestion.objects.get(pk=started.question.pk)
        assert first.timed_out and first.response_ms == 5000
        assert first.answered_at == served + timedelta(milliseconds=5000)
        assert state.question.order == 2
        assert state.question.served_at == served + timedelta(milliseconds=5800)
        assert [a.order for a in state.answers] == [1]

    def test_long_absence_times_out_everything_and_completes(self, started, clock):
        clock.move_to(T0 + timedelta(minutes=5), tick=False)
        state = services.get_current(started.session.id, started.token)
        assert state.finished and state.question is None
        s = state.session
        assert s.score == 0 and s.correct_count == 0
        assert s.total_time_ms == 20 * 5000
        assert len(state.answers) == 20

    def test_late_answer_after_absence_gets_question_mismatch_or_timeout(self, started, clock):
        sq = started.question
        clock.move_to(sq.served_at + timedelta(seconds=8), tick=False)
        result = services.submit_answer(
            started.session.id, started.token, sq.question_id, key_of(sq)
        )
        assert result.answered.timed_out  # süresi dolmuş soru için ilk (timeout) sonucu döner
        assert result.session.score == 0

    def test_session_expires_after_30_minutes(self, started, clock):
        clock.move_to(T0 + timedelta(minutes=31), tick=False)
        with pytest.raises(exc.SessionExpired):
            services.get_current(started.session.id, started.token)
        assert QuizSession.objects.get(pk=started.session.pk).status == QuizSession.Status.EXPIRED

    def test_result_requires_completed_session(self, started):
        with pytest.raises(exc.SessionNotFinished):
            services.get_result(started.session.id, started.token)

    def test_result_after_completion(self, started, clock):
        for _ in range(20):
            answer(started, after_ms=2000, clock=clock)
        state = services.get_result(started.session.id, started.token)
        assert state.finished
        assert state.session.score == 20 * 130
        assert len(state.answers) == 20
