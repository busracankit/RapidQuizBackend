"""Skor kaydı ve sıralama."""

import re
from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.db.models import Q

from apps.quiz import exceptions as exc
from apps.quiz.models import Category, QuizSession
from apps.quiz.services import run_locked

from .models import PLAYER_NAME_MAX_LENGTH, PLAYER_NAME_MIN_LENGTH, LeaderboardEntry
from .profanity import is_profane

TOP_N = 10
# Harf (tüm diller), rakam, boşluk ve - _ . ' karakterleri. HTML ve emoji dışarıda kalır.
_NAME_RE = re.compile(r"^[\w .'\-]+$")


def clean_player_name(raw) -> str:
    if not isinstance(raw, str):
        raise exc.InvalidPlayerName("İsim metin olmalı.")
    name = " ".join(raw.split())
    if not PLAYER_NAME_MIN_LENGTH <= len(name) <= PLAYER_NAME_MAX_LENGTH:
        raise exc.InvalidPlayerName(
            f"İsim {PLAYER_NAME_MIN_LENGTH}–{PLAYER_NAME_MAX_LENGTH} karakter olmalı."
        )
    if not _NAME_RE.match(name) or not any(ch.isalnum() for ch in name):
        raise exc.InvalidPlayerName(
            "İsimde yalnızca harf, rakam, boşluk ve - _ . ' kullanılabilir."
        )
    if is_profane(name):
        raise exc.InvalidPlayerName("Lütfen başka bir isim seçin.")
    return name


def rank_of(entry: LeaderboardEntry) -> int:
    """Kategorideki sırası (1'den başlar): puan ↓, süre ↑, kayıt zamanı ↑, id ↑."""
    better = LeaderboardEntry.objects.filter(category_id=entry.category_id).filter(
        Q(score__gt=entry.score)
        | Q(score=entry.score, total_time_ms__lt=entry.total_time_ms)
        | Q(score=entry.score, total_time_ms=entry.total_time_ms, created_at__lt=entry.created_at)
        | Q(
            score=entry.score,
            total_time_ms=entry.total_time_ms,
            created_at=entry.created_at,
            id__lt=entry.id,
        )
    )
    return better.count() + 1


def top_entries(category: Category, limit: int = TOP_N) -> list[LeaderboardEntry]:
    return list(LeaderboardEntry.objects.top_for_category(category, limit))


@dataclass
class SavedScore:
    entry: LeaderboardEntry
    rank: int
    top: list[LeaderboardEntry]


def save_score(session_id, token: str | None, player_name) -> SavedScore:
    """Tamamlanmış oturumun skorunu bir kez kaydeder."""
    return run_locked(session_id, token, lambda session, now: _save(session, player_name))


def _save(session: QuizSession, player_name) -> SavedScore:
    if session.status != QuizSession.Status.COMPLETED:
        raise exc.SessionNotFinished()
    if LeaderboardEntry.objects.filter(session=session).exists():
        raise exc.ScoreAlreadySaved()

    name = clean_player_name(player_name)
    try:
        with transaction.atomic():
            entry = LeaderboardEntry.objects.create(
                session=session,
                category=session.category,
                player_name=name,
                score=session.score,
                correct_count=session.correct_count,
                total_time_ms=session.total_time_ms,
            )
    except IntegrityError as e:  # eşzamanlı ikinci istek
        raise exc.ScoreAlreadySaved() from e
    return SavedScore(entry=entry, rank=rank_of(entry), top=top_entries(session.category))
