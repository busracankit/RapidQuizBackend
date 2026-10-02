"""Quiz içeriği (Category, Question, Choice) ve oyun durumu (QuizSession, SessionQuestion)."""

import hashlib
import secrets
import uuid

from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

CHOICES_PER_QUESTION = 4
QUESTION_TEXT_MAX_LENGTH = 120
CHOICE_TEXT_MAX_LENGTH = 40

hex_color_validator = RegexValidator(
    regex=r"^#[0-9A-Fa-f]{6}$",
    message="Renk #RRGGBB biçiminde olmalı (ör. #3B82F6).",
)


# --------------------------------------------------------------------------- içerik


class Category(models.Model):
    name = models.CharField("ad", max_length=60)
    slug = models.SlugField("slug", max_length=60, unique=True)
    description = models.CharField("açıklama", max_length=160, blank=True)
    icon = models.CharField(
        "ikon", max_length=40, blank=True, help_text="Frontend'deki ikon adı (ör. code, brain)."
    )
    color = models.CharField("renk", max_length=7, validators=[hex_color_validator])
    order = models.PositiveSmallIntegerField("sıra", default=0)
    is_active = models.BooleanField("aktif", default=True)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "kategori"
        verbose_name_plural = "kategoriler"

    def __str__(self) -> str:
        return self.name


class QuestionQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class Question(models.Model):
    class Difficulty(models.IntegerChoices):
        EASY = 1, "Kolay"
        MEDIUM = 2, "Orta"
        HARD = 3, "Zor"

    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="questions", verbose_name="kategori"
    )
    text = models.CharField("soru", max_length=QUESTION_TEXT_MAX_LENGTH)
    difficulty = models.PositiveSmallIntegerField(
        "zorluk", choices=Difficulty.choices, default=Difficulty.EASY
    )
    explanation = models.TextField("açıklama", blank=True)
    is_active = models.BooleanField("aktif", default=True)
    created_at = models.DateTimeField("oluşturulma", auto_now_add=True)
    updated_at = models.DateTimeField("güncellenme", auto_now=True)

    objects = QuestionQuerySet.as_manager()

    class Meta:
        ordering = ["category", "difficulty", "id"]
        verbose_name = "soru"
        verbose_name_plural = "sorular"
        indexes = [
            models.Index(fields=["category", "is_active", "difficulty"], name="question_pick_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(difficulty__gte=1) & Q(difficulty__lte=3),
                name="question_difficulty_range",
            ),
        ]

    def __str__(self) -> str:
        return self.text


class Choice(models.Model):
    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name="choices", verbose_name="soru"
    )
    text = models.CharField("şık", max_length=CHOICE_TEXT_MAX_LENGTH)
    is_correct = models.BooleanField("doğru", default=False)
    order = models.PositiveSmallIntegerField("sıra", default=0)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "şık"
        verbose_name_plural = "şıklar"
        constraints = [
            # Bir sorunun en fazla bir doğru şıkkı olabilir. "Tam 4 şık, tam 1 doğru"
            # kuralı admin formset'inde ve load_questions komutunda doğrulanır.
            models.UniqueConstraint(
                fields=["question"],
                condition=Q(is_correct=True),
                name="choice_single_correct_per_question",
            ),
        ]

    def __str__(self) -> str:
        return self.text


# --------------------------------------------------------------------------- oyun


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class QuizSession(models.Model):
    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "Devam ediyor"
        COMPLETED = "completed", "Tamamlandı"
        EXPIRED = "expired", "Süresi doldu"

    class ClientType(models.TextChoices):
        WEB = "web", "Web"
        IOS = "ios", "iOS"
        ANDROID = "android", "Android"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    token_hash = models.CharField("token hash", max_length=64, unique=True, editable=False)
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="sessions", verbose_name="kategori"
    )
    status = models.CharField(
        "durum", max_length=16, choices=Status.choices, default=Status.IN_PROGRESS
    )
    current_index = models.PositiveSmallIntegerField(
        "cevaplanan soru sayısı",
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(20)],
        help_text="0–20; cevaplanan/süresi dolan soru sayısı.",
    )
    score = models.PositiveIntegerField("puan", default=0)
    correct_count = models.PositiveSmallIntegerField("doğru sayısı", default=0)
    total_time_ms = models.PositiveIntegerField("toplam süre (ms)", default=0)
    started_at = models.DateTimeField("başlangıç", default=timezone.now)
    finished_at = models.DateTimeField("bitiş", null=True, blank=True)
    client_type = models.CharField(
        "istemci", max_length=8, choices=ClientType.choices, default=ClientType.WEB
    )

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "quiz oturumu"
        verbose_name_plural = "quiz oturumları"
        indexes = [
            models.Index(fields=["status", "started_at"], name="session_status_started_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(current_index__lte=20), name="session_current_index_max_20"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.category} · {self.get_status_display()} · {self.id}"

    @staticmethod
    def generate_token() -> tuple[str, str]:
        """Yeni bir (düz token, hash) çifti üretir. Düz token yalnızca bir kez istemciye döner."""
        token = f"tok_{secrets.token_urlsafe(32)}"
        return token, hash_session_token(token)

    def check_token(self, token: str | None) -> bool:
        if not token:
            return False
        return secrets.compare_digest(self.token_hash, hash_session_token(token))


class SessionQuestion(models.Model):
    session = models.ForeignKey(
        QuizSession,
        on_delete=models.CASCADE,
        related_name="session_questions",
        verbose_name="oturum",
    )
    question = models.ForeignKey(
        Question, on_delete=models.PROTECT, related_name="+", verbose_name="soru"
    )
    order = models.PositiveSmallIntegerField(
        "sıra", validators=[MinValueValidator(1), MaxValueValidator(20)]
    )
    choice_order = models.JSONField(
        "şık sırası", default=list, help_text="İstemciye gösterilen şık ID sırası."
    )
    served_at = models.DateTimeField(
        "gösterilme",
        null=True,
        blank=True,
        help_text="Sayacın başladığı sunucu zamanı (geri bildirim/3-2-1 kadar ileri tarihli).",
    )
    answered_at = models.DateTimeField("cevaplanma", null=True, blank=True)
    selected_choice = models.ForeignKey(
        Choice,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="seçilen şık",
    )
    is_correct = models.BooleanField("doğru mu", null=True, blank=True)
    timed_out = models.BooleanField("süre doldu", default=False)
    response_ms = models.PositiveIntegerField("cevap süresi (ms)", null=True, blank=True)
    points = models.PositiveSmallIntegerField("puan", default=0)

    class Meta:
        ordering = ["session", "order"]
        verbose_name = "oturum sorusu"
        verbose_name_plural = "oturum soruları"
        constraints = [
            models.UniqueConstraint(fields=["session", "order"], name="session_question_order"),
            models.UniqueConstraint(fields=["session", "question"], name="session_question_once"),
            models.CheckConstraint(
                condition=Q(order__gte=1) & Q(order__lte=20), name="session_question_order_range"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.session_id} #{self.order}"

    @property
    def is_answered(self) -> bool:
        return self.answered_at is not None
