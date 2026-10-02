"""Skor tablosu: yalnızca tamamlanmış ve isimlendirilmiş skorlar."""

from django.core.validators import MinLengthValidator
from django.db import models

from apps.quiz.models import Category, QuizSession

PLAYER_NAME_MIN_LENGTH = 2
PLAYER_NAME_MAX_LENGTH = 20


class LeaderboardEntryQuerySet(models.QuerySet):
    def ranked(self):
        """Sıralama: puan (büyükten küçüğe) → toplam süre (azdan çoğa) → kayıt zamanı."""
        return self.order_by("-score", "total_time_ms", "created_at", "id")

    def top_for_category(self, category, limit: int = 10):
        return self.filter(category=category).ranked()[:limit]


class LeaderboardEntry(models.Model):
    session = models.OneToOneField(
        QuizSession,
        on_delete=models.CASCADE,
        related_name="leaderboard_entry",
        verbose_name="oturum",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="leaderboard_entries",
        verbose_name="kategori",
    )
    player_name = models.CharField(
        "oyuncu adı",
        max_length=PLAYER_NAME_MAX_LENGTH,
        validators=[MinLengthValidator(PLAYER_NAME_MIN_LENGTH)],
    )
    score = models.PositiveIntegerField("puan")
    correct_count = models.PositiveSmallIntegerField("doğru sayısı")
    total_time_ms = models.PositiveIntegerField("toplam süre (ms)")
    created_at = models.DateTimeField("kayıt zamanı", auto_now_add=True)

    objects = LeaderboardEntryQuerySet.as_manager()

    class Meta:
        ordering = ["-score", "total_time_ms", "created_at"]
        verbose_name = "skor"
        verbose_name_plural = "skorlar"
        indexes = [
            models.Index(
                fields=["category", "-score", "total_time_ms", "created_at"],
                name="leaderboard_rank_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.player_name} · {self.score} ({self.category})"
