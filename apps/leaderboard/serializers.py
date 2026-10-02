from rest_framework import serializers

from apps.quiz.serializers import CategoryBriefSerializer, category_brief, iso

from .models import LeaderboardEntry


class ScoreSerializer(serializers.Serializer):
    # Uzunluk ve karakter kuralları servis katmanında (clean_player_name) uygulanır.
    player_name = serializers.CharField(
        allow_blank=True, trim_whitespace=False, max_length=100, help_text="2–20 karakter."
    )


class LeaderboardQuerySerializer(serializers.Serializer):
    category = serializers.SlugField(help_text="Kategori slug'ı.")


class EntryOutSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    rank = serializers.IntegerField()
    player_name = serializers.CharField()
    score = serializers.IntegerField()
    correct_count = serializers.IntegerField()
    total_time_ms = serializers.IntegerField()
    created_at = serializers.DateTimeField()


class LeaderboardOutSerializer(serializers.Serializer):
    category = CategoryBriefSerializer()
    entries = EntryOutSerializer(many=True)


class ScoreOutSerializer(serializers.Serializer):
    entry = EntryOutSerializer()
    rank = serializers.IntegerField()
    in_top = serializers.BooleanField(help_text="Kayıt Top 10 içinde mi?")
    leaderboard = LeaderboardOutSerializer()


def entry_payload(entry: LeaderboardEntry, rank: int) -> dict:
    return {
        "id": entry.id,
        "rank": rank,
        "player_name": entry.player_name,
        "score": entry.score,
        "correct_count": entry.correct_count,
        "total_time_ms": entry.total_time_ms,
        "created_at": iso(entry.created_at),
    }


def leaderboard_payload(category, entries) -> dict:
    return {
        "category": category_brief(category),
        "entries": [entry_payload(e, rank) for rank, e in enumerate(entries, start=1)],
    }
