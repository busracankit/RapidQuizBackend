import pytest
from django.urls import reverse

from apps.conftest import make_question
from apps.quiz.models import Choice, Question

pytestmark = pytest.mark.django_db


def _choice_rows(texts, correct_index, ids=None, question_id=None):
    data = {
        "choices-TOTAL_FORMS": str(len(texts)),
        "choices-INITIAL_FORMS": str(len(ids) if ids else 0),
        "choices-MIN_NUM_FORMS": "4",
        "choices-MAX_NUM_FORMS": "4",
    }
    for i, text in enumerate(texts):
        data[f"choices-{i}-text"] = text
        data[f"choices-{i}-order"] = str(i)
        if i == correct_index or (isinstance(correct_index, list | tuple) and i in correct_index):
            data[f"choices-{i}-is_correct"] = "on"
        if ids:
            data[f"choices-{i}-id"] = str(ids[i])
            data[f"choices-{i}-question"] = str(question_id)
    return data


def _question_data(category, text="Başkenti Ankara olan ülke?"):
    return {
        "category": str(category.pk),
        "text": text,
        "difficulty": "1",
        "explanation": "",
        "is_active": "on",
    }


class TestQuestionAdminValidation:
    url = reverse("admin:quiz_question_add")

    def test_valid_question_with_four_choices(self, admin_client, category):
        data = _question_data(category) | _choice_rows(
            ["Türkiye", "Yunanistan", "Irak", "Mısır"], 0
        )
        response = admin_client.post(self.url, data)
        assert response.status_code == 302, response.context["errors"]
        q = Question.objects.get()
        assert q.choices.count() == 4
        assert q.choices.get(is_correct=True).text == "Türkiye"

    def test_rejects_fewer_than_four_choices(self, admin_client, category):
        data = _question_data(category) | _choice_rows(["A", "B", "C"], 0)
        response = admin_client.post(self.url, data)
        assert response.status_code == 200
        assert Question.objects.count() == 0

    def test_rejects_no_correct_choice(self, admin_client, category):
        data = _question_data(category) | _choice_rows(["A", "B", "C", "D"], None)
        response = admin_client.post(self.url, data)
        assert response.status_code == 200
        assert "tam 1 doğru" in str(
            response.context["inline_admin_formsets"][0].formset.non_form_errors()
        )
        assert Question.objects.count() == 0

    def test_rejects_two_correct_choices(self, admin_client, category):
        data = _question_data(category) | _choice_rows(["A", "B", "C", "D"], [0, 2])
        response = admin_client.post(self.url, data)
        assert response.status_code == 200
        assert Question.objects.count() == 0

    def test_rejects_duplicate_choice_texts(self, admin_client, category):
        data = _question_data(category) | _choice_rows(["A", "b", "B ", "D"], 0)
        response = admin_client.post(self.url, data)
        assert response.status_code == 200
        assert Question.objects.count() == 0

    def test_rejects_too_long_question_text(self, admin_client, category):
        data = _question_data(category, text="x" * 121) | _choice_rows(["A", "B", "C", "D"], 0)
        response = admin_client.post(self.url, data)
        assert response.status_code == 200
        assert Question.objects.count() == 0


class TestChangingCorrectChoice:
    """Tek doğru şık kısıtı (partial unique) kayıt sırasından bağımsız çalışmalı."""

    @pytest.mark.parametrize(("old_correct", "new_correct"), [(0, 3), (3, 0), (1, 2), (2, 1)])
    def test_move_correct_choice(self, admin_client, category, old_correct, new_correct):
        q = make_question(category, correct=old_correct)
        ids = list(q.choices.order_by("order").values_list("id", flat=True))
        texts = list(q.choices.order_by("order").values_list("text", flat=True))
        data = _question_data(category, text=q.text) | _choice_rows(
            texts, new_correct, ids=ids, question_id=q.pk
        )
        response = admin_client.post(reverse("admin:quiz_question_change", args=[q.pk]), data)
        assert response.status_code == 302
        assert Choice.objects.get(question=q, is_correct=True).id == ids[new_correct]


class TestAdminPages:
    @pytest.mark.parametrize(
        "name",
        [
            "admin:quiz_category_changelist",
            "admin:quiz_question_changelist",
            "admin:quiz_question_add",
            "admin:quiz_quizsession_changelist",
            "admin:leaderboard_leaderboardentry_changelist",
        ],
    )
    def test_pages_load(self, admin_client, question, name):
        assert admin_client.get(reverse(name)).status_code == 200

    def test_question_change_page_loads(self, admin_client, question):
        url = reverse("admin:quiz_question_change", args=[question.pk])
        assert admin_client.get(url).status_code == 200

    def test_session_detail_is_read_only(self, admin_client, quiz_session):
        assert admin_client.get(reverse("admin:quiz_quizsession_add")).status_code == 403
        url = reverse("admin:quiz_quizsession_change", args=[quiz_session.pk])
        response = admin_client.get(url)
        assert response.status_code == 200
        assert "token_hash" not in response.content.decode()

    def test_category_list_shows_active_question_count(self, admin_client, category):
        make_question(category, text="Aktif 1")
        make_question(category, text="Aktif 2")
        make_question(category, text="Pasif", is_active=False)
        response = admin_client.get(reverse("admin:quiz_category_changelist"))
        cl = response.context["cl"]
        counts = {c.slug: c._active_questions for c in cl.result_list}
        assert counts["yazilim"] == 2
        assert counts["fizik"] == 0

    def test_bulk_deactivate_action(self, admin_client, category):
        q = make_question(category)
        response = admin_client.post(
            reverse("admin:quiz_question_changelist"),
            {"action": "deactivate", "_selected_action": [q.pk]},
        )
        assert response.status_code == 302
        q.refresh_from_db()
        assert q.is_active is False
