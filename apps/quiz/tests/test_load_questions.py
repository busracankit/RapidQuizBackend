import json
from io import StringIO
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import CommandError, call_command

from apps.conftest import make_session
from apps.quiz.loaders import load_payload, validate_payload
from apps.quiz.models import Category, Choice, Question, SessionQuestion

pytestmark = pytest.mark.django_db

DATA_DIR = Path(settings.BASE_DIR) / "data" / "questions"


def payload(**overrides):
    q = {
        "text": "Türkiye'nin başkenti neresidir?",
        "difficulty": 1,
        "correct": "Ankara",
        "wrong": ["İstanbul", "İzmir", "Bursa"],
    }
    q.update(overrides)
    return {
        "category": {"slug": "ulkeler", "name": "Ülkeler", "color": "#10B981"},
        "questions": [q],
    }


def write(tmp_path, data, name="test.json"):
    path = tmp_path / name
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return str(path)


def run(*args):
    out, err = StringIO(), StringIO()
    call_command("load_questions", *args, stdout=out, stderr=err)
    return out.getvalue(), err.getvalue()


class TestValidation:
    def test_valid_payload(self):
        assert validate_payload(payload()) == []

    @pytest.mark.parametrize(
        ("override", "fragment"),
        [
            ({"text": "x" * 121}, "en fazla 120"),
            ({"text": ""}, "'text' zorunlu"),
            ({"difficulty": 4}, "difficulty"),
            ({"difficulty": "1"}, "difficulty"),
            ({"correct": ""}, "'correct' zorunlu"),
            ({"wrong": ["a", "b"]}, "tam 3"),
            ({"wrong": ["a", "b", "x" * 41]}, "en fazla 40"),
            ({"wrong": ["İstanbul", "ankara ", "Bursa"]}, "farklı olmalı"),
        ],
    )
    def test_invalid_question(self, override, fragment):
        errors = validate_payload(payload(**override))
        assert any(fragment in e for e in errors), errors

    def test_duplicate_question_in_file(self):
        data = payload()
        data["questions"].append(dict(data["questions"][0]))
        assert any("birden fazla" in e for e in validate_payload(data))

    def test_bad_category(self):
        data = payload()
        data["category"] = {"slug": "", "color": "mavi"}
        errors = validate_payload(data)
        assert len(errors) == 3


class TestLoading:
    def test_creates_question_with_one_correct_choice(self):
        result = load_payload(payload())
        assert result.created == 1
        q = Question.objects.get(text="Türkiye'nin başkenti neresidir?")
        assert q.category.slug == "ulkeler"
        assert q.choices.count() == 4
        assert q.choices.get(is_correct=True).text == "Ankara"

    def test_is_idempotent(self):
        load_payload(payload())
        result = load_payload(payload())
        assert (result.created, result.updated, result.unchanged) == (0, 0, 1)
        assert Question.objects.count() == 1
        assert Choice.objects.count() == 4

    def test_updates_choices_in_place_even_if_played(self, category):
        load_payload(payload())
        q = Question.objects.get()
        old_ids = set(q.choices.values_list("id", flat=True))
        played = q.choices.get(text="İzmir")
        session = make_session(q.category)
        SessionQuestion.objects.create(session=session, question=q, order=1, selected_choice=played)

        result = load_payload(
            payload(correct="Ankara", wrong=["Konya", "İzmir", "Bursa"], difficulty=2)
        )

        assert result.updated == 1
        q.refresh_from_db()
        assert q.difficulty == 2
        assert set(q.choices.values_list("id", flat=True)) == old_ids
        assert sorted(q.choices.values_list("text", flat=True)) == [
            "Ankara",
            "Bursa",
            "Konya",
            "İzmir",
        ]
        assert q.choices.filter(is_correct=True).count() == 1

    def test_changing_correct_answer(self):
        load_payload(payload())
        load_payload(payload(correct="Bursa", wrong=["İstanbul", "İzmir", "Ankara"]))
        q = Question.objects.get()
        assert q.choices.get(is_correct=True).text == "Bursa"

    def test_updates_category_fields(self):
        data = payload()
        data["category"]["description"] = "Yeni açıklama"
        load_payload(data)
        assert Category.objects.get(slug="ulkeler").description == "Yeni açıklama"

    def test_deactivate_missing(self, category):
        load_payload(payload())
        other = Question.objects.create(
            category=Category.objects.get(slug="ulkeler"), text="Eski soru"
        )
        result = load_payload(payload(), deactivate_missing=True)
        other.refresh_from_db()
        assert result.deactivated == 1
        assert other.is_active is False


class TestCommand:
    def test_check_only_does_not_write(self, tmp_path):
        out, _ = run(write(tmp_path, payload()), "--check")
        assert "1 soru geçerli" in out
        assert Question.objects.count() == 0

    def test_any_invalid_file_aborts_everything(self, tmp_path):
        good = write(tmp_path, payload(), "good.json")
        bad = write(tmp_path, payload(difficulty=9), "bad.json")
        with pytest.raises(CommandError):
            run(good, bad)
        assert Question.objects.count() == 0

    def test_invalid_json(self, tmp_path):
        path = tmp_path / "broken.json"
        path.write_text("{oops", encoding="utf-8")
        with pytest.raises(CommandError):
            run(str(path))

    def test_warns_when_difficulty_mix_is_short(self, tmp_path):
        out, _ = run(write(tmp_path, payload()))
        assert "uyarı" in out


class TestShippedQuestionFiles:
    """data/questions altındaki gerçek dosyalar kurallara uymalı."""

    @pytest.mark.parametrize("path", sorted(DATA_DIR.glob("*.json")), ids=lambda p: p.stem)
    def test_file_is_valid_and_meets_difficulty_mix(self, path):
        data = json.loads(path.read_text(encoding="utf-8"))
        assert validate_payload(data) == []
        counts = {d: sum(1 for q in data["questions"] if q["difficulty"] == d) for d in (1, 2, 3)}
        for difficulty, need in settings.QUIZ_DIFFICULTY_MIX.items():
            assert counts[difficulty] >= need
        assert path.stem == data["category"]["slug"]

    def test_all_five_categories_have_files(self):
        slugs = {p.stem for p in DATA_DIR.glob("*.json")}
        assert slugs == set(Category.objects.values_list("slug", flat=True))

    def test_loading_all_files(self):
        out, _ = run()
        assert "uyarı" not in out
        for category in Category.objects.all():
            assert category.questions.filter(is_active=True).count() >= 20
        assert Choice.objects.filter(is_correct=True).count() == Question.objects.count()
