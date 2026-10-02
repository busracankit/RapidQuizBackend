"""v1 API uçtan uca testleri (DRF APIClient, zaman time-machine ile dondurulur)."""

from datetime import UTC, datetime, timedelta

import pytest
from rest_framework.test import APIClient

from apps.leaderboard.models import LeaderboardEntry
from apps.quiz.models import QuizSession, SessionQuestion

pytestmark = pytest.mark.django_db

T0 = datetime(2026, 10, 1, 12, 0, 0, tzinfo=UTC)
API = "/api/v1"


@pytest.fixture
def clock(time_machine):
    time_machine.move_to(T0, tick=False)
    return time_machine


@pytest.fixture
def api():
    return APIClient()


def assert_error(response, status, code):
    assert response.status_code == status, response.content
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == code
    assert body["error"]["message"]


def start(api, slug="yazilim", **extra):
    return api.post(f"{API}/sessions/", {"category": slug, **extra}, format="json")


def auth(token):
    return {"HTTP_X_SESSION_TOKEN": token}


def correct_key(session_id, question_payload):
    sq = SessionQuestion.objects.select_related("question").get(
        session_id=session_id, question_id=question_payload["id"]
    )
    by_id = {c.id: c for c in sq.question.choices.all()}
    return next(i for i, db_id in enumerate(sq.choice_order, 1) if by_id[db_id].is_correct)


class Game:
    """Bir oyunu API üzerinden oynatan küçük yardımcı."""

    def __init__(self, api, clock, slug="yazilim"):
        self.api, self.clock = api, clock
        r = start(api, slug)
        assert r.status_code == 201, r.content
        self.data = r.json()
        self.id = self.data["session_id"]
        self.token = self.data["session_token"]
        self.question = self.data["question"]

    def url(self, part):
        return f"{API}/sessions/{self.id}/{part}/"

    def answer(self, *, after_ms=1000, correct=True, choice=..., question_id=None):
        served = datetime.fromisoformat(self.question["served_at"])
        self.clock.move_to(served + timedelta(milliseconds=after_ms), tick=False)
        if choice is ...:
            key = correct_key(self.id, self.question)
            choice = key if correct else key % 4 + 1
        r = self.api.post(
            self.url("answers"),
            {"question_id": question_id or self.question["id"], "choice_id": choice},
            format="json",
            **auth(self.token),
        )
        if r.status_code == 200 and r.json()["next_question"]:
            self.question = r.json()["next_question"]
        return r

    def play_all(self, **kw):
        for _ in range(20):
            r = self.answer(**kw)
            assert r.status_code == 200, r.content
        return r


@pytest.fixture
def game(api, full_category, clock):
    return Game(api, clock, full_category.slug)


# --------------------------------------------------------------------------- kategoriler


def test_categories_list(api):
    r = api.get(f"{API}/categories/")
    assert r.status_code == 200
    body = r.json()
    assert [c["slug"] for c in body] == [
        "yazilim",
        "yapay-zeka",
        "bilgisayar-muhendisligi",
        "ulkeler",
        "fizik",
    ]
    assert set(body[0]) == {"slug", "name", "description", "icon", "color", "order"}


def test_inactive_categories_hidden(api, category):
    category.is_active = False
    category.save()
    slugs = [c["slug"] for c in api.get(f"{API}/categories/").json()]
    assert "yazilim" not in slugs


# --------------------------------------------------------------------------- oturum açma


class TestCreateSession:
    def test_returns_first_question_without_answer(self, game):
        d = game.data
        assert d["total_questions"] == 20 and d["time_limit_ms"] == 5000
        assert d["category"] == {"slug": "yazilim", "name": "Yazılım", "color": "#3B82F6"}
        assert d["session_token"].startswith("tok_")
        q = d["question"]
        assert q["index"] == 1
        assert q["starts_in_ms"] == 3000 and q["remaining_ms"] == 5000
        assert q["served_at"] == "2026-10-01T12:00:03Z"
        assert [c["id"] for c in q["choices"]] == [1, 2, 3, 4]
        assert all(set(c) == {"id", "text"} for c in q["choices"])
        assert "is_correct" not in str(d) and "correct" not in q

    def test_token_is_not_stored_in_plain_text(self, game):
        session = QuizSession.objects.get(pk=game.id)
        assert session.token_hash != game.token

    def test_validation_error(self, api):
        assert_error(api.post(f"{API}/sessions/", {}, format="json"), 400, "validation_error")
        r = start(api, client_type="windows-phone")
        assert_error(r, 400, "validation_error")
        assert "client_type" in r.json()["error"]["details"]

    def test_unknown_category(self, api):
        assert_error(start(api, "yok"), 404, "category_not_found")

    def test_not_enough_questions(self, api, category):
        assert_error(start(api, "yazilim"), 409, "not_enough_questions")

    def test_invalid_json(self, api):
        r = api.post(f"{API}/sessions/", "{oops", content_type="application/json")
        assert_error(r, 400, "invalid_json")

    def test_wrong_method(self, api):
        assert_error(api.get(f"{API}/sessions/"), 405, "method_not_allowed")


# --------------------------------------------------------------------------- cevap


class TestAnswer:
    def test_correct_answer_and_next_question(self, game):
        r = game.answer(after_ms=1800)
        assert r.status_code == 200
        body = r.json()
        assert body["is_correct"] is True and body["timed_out"] is False
        assert body["points"] == 132 and body["score"] == 132
        assert body["correct_choice_id"] == body["selected_choice_id"]
        assert body["answered_count"] == 1 and body["finished"] is False
        nxt = body["next_question"]
        assert nxt["index"] == 2
        assert nxt["starts_in_ms"] == 800 and nxt["remaining_ms"] == 5000

    def test_wrong_answer_reveals_correct_choice(self, game):
        body = game.answer(correct=False).json()
        assert body["is_correct"] is False and body["points"] == 0
        assert body["correct_choice_id"] != body["selected_choice_id"]
        assert 1 <= body["correct_choice_id"] <= 4

    def test_timeout_with_null_choice(self, game):
        body = game.answer(after_ms=5000, choice=None).json()
        assert body["timed_out"] is True and body["points"] == 0
        assert body["selected_choice_id"] is None

    def test_late_answer_is_timed_out(self, game):
        body = game.answer(after_ms=6000).json()
        assert body["timed_out"] is True and body["points"] == 0

    def test_duplicate_answer_returns_first_result(self, game):
        q = game.question
        first = game.answer(after_ms=1000).json()
        game.question = q
        again = game.answer(after_ms=1200, correct=False).json()
        assert again == {**first, "next_question": again["next_question"]}
        assert again["score"] == first["score"]

    def test_stale_question_conflict(self, game):
        future = SessionQuestion.objects.get(session_id=game.id, order=5)
        r = game.answer(question_id=future.question_id)
        assert_error(r, 409, "question_mismatch")

    @pytest.mark.parametrize("choice", [0, 5, "a"])
    def test_invalid_choice(self, game, choice):
        assert_error(game.answer(choice=choice), 400, "validation_error")

    def test_choice_id_is_required(self, game, api):
        r = api.post(
            game.url("answers"),
            {"question_id": game.question["id"]},
            format="json",
            **auth(game.token),
        )
        assert_error(r, 400, "validation_error")

    def test_missing_and_wrong_token(self, game, api):
        payload = {"question_id": game.question["id"], "choice_id": 1}
        assert_error(
            api.post(game.url("answers"), payload, format="json"), 403, "invalid_session_token"
        )
        r = api.post(game.url("answers"), payload, format="json", **auth("tok_baska"))
        assert_error(r, 403, "invalid_session_token")

    @pytest.mark.parametrize("sid", ["00000000-0000-0000-0000-000000000000", "abc"])
    def test_unknown_session(self, api, sid):
        r = api.get(f"{API}/sessions/{sid}/current/", **auth("tok_x"))
        assert_error(r, 404, "session_not_found")


# --------------------------------------------------------------------------- devam / sonuç / skor


class TestFlow:
    def test_current_after_refresh(self, game, api):
        game.answer(after_ms=1000)
        r = api.get(game.url("current"), **auth(game.token))
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "in_progress" and body["answered_count"] == 1
        assert body["question"]["index"] == 2
        assert body["answers"] == [
            {"index": 1, "is_correct": True, "timed_out": False, "points": 140, "response_ms": 1000}
        ]

    def test_current_closes_overdue_questions(self, game, api, clock):
        clock.move_to(T0 + timedelta(seconds=3 + 5.8 + 5.8 + 1), tick=False)
        body = api.get(game.url("current"), **auth(game.token)).json()
        assert body["answered_count"] == 2
        assert [a["timed_out"] for a in body["answers"]] == [True, True]
        assert body["question"]["index"] == 3

    def test_result_before_finish(self, game, api):
        assert_error(api.get(game.url("result"), **auth(game.token)), 409, "session_not_finished")

    def test_full_game_result_score_and_leaderboard(self, game, api):
        last = game.play_all(after_ms=500)
        assert last.json()["finished"] is True and last.json()["next_question"] is None
        assert last.json()["score"] == 20 * 145

        result = api.get(game.url("result"), **auth(game.token)).json()
        assert result["score"] == 2900 and result["max_score"] == 3000
        assert result["correct_count"] == 20 and result["total_time_ms"] == 10000
        assert result["score_saved"] is False and result["rank"] is None
        assert len(result["answers"]) == 20

        r = api.post(
            game.url("score"), {"player_name": " Ayşe "}, format="json", **auth(game.token)
        )
        assert r.status_code == 201, r.content
        body = r.json()
        assert body["rank"] == 1 and body["in_top"] is True
        assert body["entry"]["player_name"] == "Ayşe" and body["entry"]["score"] == 2900
        assert body["leaderboard"]["entries"][0]["id"] == body["entry"]["id"]

        result = api.get(game.url("result"), **auth(game.token)).json()
        assert result["score_saved"] is True and result["player_name"] == "Ayşe"
        assert result["rank"] == 1

        board = api.get(f"{API}/leaderboard/", {"category": "yazilim"}).json()
        assert board["category"]["slug"] == "yazilim"
        assert board["entries"][0]["player_name"] == "Ayşe"
        assert board["entries"][0]["rank"] == 1

    def test_score_twice_conflict(self, game, api):
        game.play_all()
        url, h = game.url("score"), auth(game.token)
        assert api.post(url, {"player_name": "Ali"}, format="json", **h).status_code == 201
        assert_error(
            api.post(url, {"player_name": "Veli"}, format="json", **h), 409, "score_already_saved"
        )

    def test_score_before_finish(self, game, api):
        r = api.post(game.url("score"), {"player_name": "Ali"}, format="json", **auth(game.token))
        assert_error(r, 409, "session_not_finished")

    @pytest.mark.parametrize("name", ["A", "<script>", "orospu", ""])
    def test_invalid_names(self, game, api, name):
        game.play_all()
        r = api.post(game.url("score"), {"player_name": name}, format="json", **auth(game.token))
        assert_error(r, 400, "invalid_player_name")

    def test_expired_session(self, game, api, clock):
        clock.move_to(T0 + timedelta(minutes=31), tick=False)
        assert_error(api.get(game.url("current"), **auth(game.token)), 410, "session_expired")
        assert QuizSession.objects.get(pk=game.id).status == "expired"


# --------------------------------------------------------------------------- skor tablosu


class TestLeaderboard:
    def test_requires_category(self, api):
        assert_error(api.get(f"{API}/leaderboard/"), 400, "validation_error")

    def test_unknown_category(self, api):
        assert_error(api.get(f"{API}/leaderboard/", {"category": "yok"}), 404, "category_not_found")

    def test_empty(self, api):
        body = api.get(f"{API}/leaderboard/", {"category": "fizik"}).json()
        assert body["entries"] == [] and body["category"]["name"] == "Fizik"

    def test_top_ten_order(self, api, full_category, clock):
        from apps.conftest import make_session

        for i in range(12):
            LeaderboardEntry.objects.create(
                session=make_session(full_category, status="completed"),
                category=full_category,
                player_name=f"P{i:02d}",
                score=100 * i,
                correct_count=i,
                total_time_ms=1000,
            )
        entries = api.get(f"{API}/leaderboard/", {"category": "yazilim"}).json()["entries"]
        assert len(entries) == 10
        assert [e["player_name"] for e in entries[:3]] == ["P11", "P10", "P09"]
        assert [e["rank"] for e in entries] == list(range(1, 11))


# --------------------------------------------------------------------------- altyapı


class TestInfrastructure:
    def test_unknown_api_url_is_json_404(self, api):
        assert_error(api.get("/api/v1/yok/"), 404, "not_found")

    def test_cors_allows_frontend_and_session_header(self, api, settings):
        settings.CORS_ALLOWED_ORIGINS = ["https://rapidquiz.app"]
        r = api.options(
            f"{API}/sessions/",
            HTTP_ORIGIN="https://rapidquiz.app",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="content-type,x-session-token",
        )
        assert r.headers["Access-Control-Allow-Origin"] == "https://rapidquiz.app"
        assert "x-session-token" in r.headers["Access-Control-Allow-Headers"]

    def test_cors_rejects_other_origins(self, api, settings):
        settings.CORS_ALLOWED_ORIGINS = ["https://rapidquiz.app"]
        r = api.get(f"{API}/categories/", HTTP_ORIGIN="https://evil.example.com")
        assert "Access-Control-Allow-Origin" not in r.headers

    def test_no_cookies_or_csrf_needed(self, full_category, clock):
        client = APIClient(enforce_csrf_checks=True)
        r = start(client)
        assert r.status_code == 201
        assert not r.cookies

    def test_rate_limit_on_session_create(self, api, full_category, clock, monkeypatch):
        from rest_framework.throttling import ScopedRateThrottle

        monkeypatch.setitem(ScopedRateThrottle.THROTTLE_RATES, "session_create", "2/min")
        assert start(api).status_code == 201
        assert start(api).status_code == 201
        r = start(api)
        assert_error(r, 429, "rate_limited")
        assert "Retry-After" in r.headers

    def test_openapi_schema(self, api):
        r = api.get("/api/schema/")
        assert r.status_code == 200
        text = r.content.decode()
        for path in [
            "/api/v1/sessions/",
            "/api/v1/sessions/{session_id}/answers/",
            "/api/v1/leaderboard/",
        ]:
            assert path in text
        assert "X-Session-Token" in text

    def test_swagger_ui_served_locally(self, api):
        r = api.get("/api/docs/")
        assert r.status_code == 200
        assert "cdn.jsdelivr" not in r.content.decode()
