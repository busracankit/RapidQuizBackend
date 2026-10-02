from django.contrib import admin

from .models import LeaderboardEntry


@admin.register(LeaderboardEntry)
class LeaderboardEntryAdmin(admin.ModelAdmin):
    """Skorlar oyundan gelir; admin yalnızca isim moderasyonu (düzenle/sil) yapar."""

    list_display = (
        "player_name",
        "category",
        "score",
        "correct_count",
        "total_time_ms",
        "created_at",
    )
    list_filter = ("category",)
    search_fields = ("player_name",)
    list_select_related = ("category",)
    ordering = ("category", "-score", "total_time_ms", "created_at")
    fields = (
        "player_name",
        "category",
        "score",
        "correct_count",
        "total_time_ms",
        "session",
        "created_at",
    )
    readonly_fields = (
        "category",
        "score",
        "correct_count",
        "total_time_ms",
        "session",
        "created_at",
    )

    def has_add_permission(self, request):
        return False
