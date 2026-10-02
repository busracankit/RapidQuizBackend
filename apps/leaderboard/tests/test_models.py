from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.urls import reverse
from django.utils import timezone

from apps.conftest import make_session
from apps.leaderboard.models import LeaderboardEntry
from apps.quiz.models import Category

pytestmark = pytest.mark.django_db


def make_entry(category, name="Ayşe", score=1000, total_time_ms=30000, **kw):
    session = make_session(category, status="completed")
    return LeaderboardEntry.objects.create(
        session=session,
        category=category,
        player_name=name,
        score=score,
        correct_count=kw.pop("correct_count", 10),
        total_time_ms=total_time_ms,
        **kw,
    )


def test_ranking_score_then_time_then_created_at(category):
    late_tie = make_entry(category, "Geç", score=2000, total_time_ms=40000)
    early_tie = make_entry(category, "Erken", score=2000, total_time_ms=40000)
    # Kayıt zamanını açıkça ayır: "Erken" önce kaydedilmiş olsun.
    LeaderboardEntry.objects.filter(pk=early_tie.pk).update(
        created_at=timezone.now() - timedelta(minutes=5)
    )
    fast = make_entry(category, "Hızlı", score=2000, total_time_ms=20000)
    top = make_entry(category, "Lider", score=2500, total_time_ms=60000)
    low = make_entry(category, "Son", score=100)

    names = [e.player_name for e in LeaderboardEntry.objects.filter(category=category).ranked()]
    assert names == ["Lider", "Hızlı", "Erken", "Geç", "Son"]
    assert {top, fast, late_tie, low}  # kullanılmayan değişken uyarısı olmasın


def test_top_for_category_limits_to_10_and_filters_category(category):
    other = Category.objects.get(slug="fizik")
    for i in range(12):
        make_entry(category, f"Oyuncu{i}", score=100 + i)
    make_entry(other, "Fizikçi", score=9999)

    top = list(LeaderboardEntry.objects.top_for_category(category))
    assert len(top) == 10
    assert top[0].player_name == "Oyuncu11"
    assert all(e.category_id == category.id for e in top)


def test_same_name_can_appear_multiple_times(category):
    make_entry(category, "Ali", score=500)
    make_entry(category, "Ali", score=700)
    assert LeaderboardEntry.objects.filter(player_name="Ali").count() == 2


def test_session_can_be_scored_only_once(category):
    entry = make_entry(category)
    with pytest.raises(IntegrityError):
        LeaderboardEntry.objects.create(
            session=entry.session,
            category=category,
            player_name="Tekrar",
            score=1,
            correct_count=1,
            total_time_ms=1,
        )


@pytest.mark.parametrize("name", ["A", "x" * 21])
def test_player_name_length(category, name):
    session = make_session(category)
    entry = LeaderboardEntry(
        session=session,
        category=category,
        player_name=name,
        score=0,
        correct_count=0,
        total_time_ms=0,
    )
    with pytest.raises(ValidationError) as exc:
        entry.full_clean()
    assert "player_name" in exc.value.message_dict


def test_admin_cannot_add_entries(admin_client):
    assert admin_client.get(reverse("admin:leaderboard_leaderboardentry_add")).status_code == 403


def test_admin_can_rename_entry(admin_client, category):
    entry = make_entry(category, "Kötüİsim")
    url = reverse("admin:leaderboard_leaderboardentry_change", args=[entry.pk])
    response = admin_client.post(url, {"player_name": "Oyuncu"})
    assert response.status_code == 302
    entry.refresh_from_db()
    assert entry.player_name == "Oyuncu"
    assert entry.score == 1000
