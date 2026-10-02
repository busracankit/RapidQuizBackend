from datetime import UTC, datetime, timedelta

import pytest

from apps.leaderboard import services as lb
from apps.leaderboard.models import LeaderboardEntry
from apps.leaderboard.profanity import is_profane
from apps.quiz import exceptions as exc
from apps.quiz import services
from apps.quiz.models import QuizSession

pytestmark = pytest.mark.django_db

T0 = datetime(2026, 10, 1, 12, 0, 0, tzinfo=UTC)


def play(category, clock, *, after_ms=1000, correct=True):
    """Tam bir oyun oynar, (session_id, token) döner."""
    started = services.start_session(category.slug)
    for _ in range(20):
        s = QuizSession.objects.get(pk=started.session.pk)
        sq = s.session_questions.select_related("question").get(order=s.current_index + 1)
        clock.move_to(sq.served_at + timedelta(milliseconds=after_ms), tick=False)
        key = services.correct_choice_id(sq)
        if not correct:
            key = key % 4 + 1
        services.submit_answer(s.id, started.token, sq.question_id, key)
    return started.session.id, started.token


@pytest.fixture
def clock(time_machine):
    time_machine.move_to(T0, tick=False)
    return time_machine


class TestCleanPlayerName:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("  Ayşe  ", "Ayşe"),
            ("Çağrı   Öztürk", "Çağrı Öztürk"),
            ("ab", "ab"),
            ("x" * 20, "x" * 20),
            ("O'Neil-2_k.", "O'Neil-2_k."),
            ("İğdır", "İğdır"),
        ],
    )
    def test_valid(self, raw, expected):
        assert lb.clean_player_name(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        ["a", " a ", "x" * 21, "", "<b>Ali</b>", "Ali 🚀", "---", "a;drop", None, 42],
    )
    def test_invalid(self, raw):
        with pytest.raises(exc.InvalidPlayerName):
            lb.clean_player_name(raw)

    @pytest.mark.parametrize(
        "raw", ["orospu", "Or0spu cocugu", "o r o s p u", "FUCK", "siktir git", "amk", "pezevenk1"]
    )
    def test_profanity_rejected(self, raw):
        with pytest.raises(exc.InvalidPlayerName):
            lb.clean_player_name(raw)

    @pytest.mark.parametrize(
        "name", ["Sıkıcı Ali", "Götürücü", "Amasya", "Sikke", "Picasso", "Bokser", "Dickens"]
    )
    def test_no_false_positives(self, name):
        assert not is_profane(name)


class TestSaveScore:
    def test_saves_completed_session(self, full_category, clock):
        session_id, token = play(full_category, clock)
        saved = lb.save_score(session_id, token, "  Ayşe ")
        assert saved.entry.player_name == "Ayşe"
        assert saved.entry.score == 20 * 140
        assert saved.entry.correct_count == 20
        assert saved.entry.total_time_ms == 20 * 1000
        assert saved.entry.category_id == full_category.id
        assert saved.rank == 1
        assert [e.pk for e in saved.top] == [saved.entry.pk]

    def test_only_once(self, full_category, clock):
        session_id, token = play(full_category, clock)
        lb.save_score(session_id, token, "Ayşe")
        with pytest.raises(exc.ScoreAlreadySaved):
            lb.save_score(session_id, token, "Başka")
        assert LeaderboardEntry.objects.count() == 1

    def test_requires_completed_session(self, full_category, clock):
        started = services.start_session(full_category.slug)
        with pytest.raises(exc.SessionNotFinished):
            lb.save_score(started.session.id, started.token, "Ayşe")

    def test_invalid_name_does_not_consume_the_save(self, full_category, clock):
        session_id, token = play(full_category, clock)
        with pytest.raises(exc.InvalidPlayerName):
            lb.save_score(session_id, token, "x")
        assert lb.save_score(session_id, token, "Ayşe").rank == 1

    def test_wrong_token(self, full_category, clock):
        session_id, _ = play(full_category, clock)
        with pytest.raises(exc.InvalidSessionToken):
            lb.save_score(session_id, "tok_baskasi", "Ayşe")

    def test_rank_uses_score_then_time_then_created_at(self, full_category, clock):
        fast = play(full_category, clock, after_ms=500)  # 20 × 145
        slow = play(full_category, clock, after_ms=2000)  # 20 × 130
        lb.save_score(*slow, "Yavaş")
        saved = lb.save_score(*fast, "Hızlı")
        assert saved.rank == 1
        assert [e.player_name for e in saved.top] == ["Hızlı", "Yavaş"]

        # Aynı puan ve süre: önce kaydeden önde.
        tie = play(full_category, clock, after_ms=500)
        clock.shift(timedelta(seconds=1))
        assert lb.save_score(*tie, "Geç Gelen").rank == 2

    def test_rank_beyond_top_ten(self, full_category, clock):
        for i in range(10):
            lb.save_score(*play(full_category, clock, after_ms=100), f"Usta{i}")
        saved = lb.save_score(*play(full_category, clock, correct=False), "Çaylak")
        assert saved.rank == 11
        assert len(saved.top) == 10
        assert saved.entry not in saved.top
