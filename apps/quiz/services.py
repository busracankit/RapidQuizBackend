"""Oyun kuralları: oturum açma, soru sunma, cevap değerlendirme, süre ve puan.

İş kuralları yalnızca burada yaşar; view'lar ve istemciler bunları yalnızca gösterir.
Tüm zamanlar sunucu saatidir (UTC).

Süre modeli
-----------
Şık kimlikleri
--------------
İstemciye şıkların veritabanı kimlikleri gönderilmez: yükleme sırasında doğru şık
çoğunlukla ilk oluşturulduğu için en küçük kimlik doğru cevabı ele verebilirdi.
Bunun yerine her soru için oturuma özel 1–4 arası kimlikler kullanılır
(`SessionQuestion.choice_order` içindeki sıra + 1).

- Her sorunun sayacı `served_at` anında başlar. Sunucu `served_at`'i istemcinin
  göstereceği bekleme kadar ileri tarihler: ilk soruda 3-2-1 sayımı
  (`QUIZ_READY_COUNTDOWN_MS`), sonrakilerde doğru/yanlış geri bildirimi (`QUIZ_FEEDBACK_MS`).
- Cevap `served_at + limit + tolerans` (5000 + 750 ms) içinde gelirse geçerlidir;
  puanda süre en fazla `limit` alınır. Daha geç gelen cevap "süre doldu" sayılır.
- İstemci sessiz kalırsa (sekme kapandı, ağ koptu) sunucu, istemcinin yapacağını
  taklit eder: süresi dolan soruyu "süre doldu" kaydeder ve bir sonrakinin sayacını
  `önceki served_at + limit + geri bildirim` anında başlatır. Böylece yenileme ile
  süre kazanılamaz.
"""

import math
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from . import exceptions as exc
from .models import Category, Question, QuizSession, SessionQuestion

BASE_POINTS = 100
MAX_SPEED_BONUS = 50
_rng = secrets.SystemRandom()


# --------------------------------------------------------------------------- yardımcılar


def _ms(value: int) -> timedelta:
    return timedelta(milliseconds=value)


def _elapsed_ms(start: datetime, end: datetime) -> int:
    return (end - start) // timedelta(milliseconds=1)


def time_limit_ms() -> int:
    return settings.QUIZ_TIME_LIMIT_MS


def questions_per_session() -> int:
    return settings.QUIZ_QUESTIONS_PER_SESSION


def calculate_points(is_correct: bool, response_ms: int) -> int:
    """Doğru cevap: 100 taban + kalan süreye göre en fazla 50 hız bonusu."""
    if not is_correct:
        return 0
    limit = time_limit_ms()
    r = min(max(response_ms, 0), limit)
    return BASE_POINTS + math.floor(MAX_SPEED_BONUS * (limit - r) / limit)


def answer_deadline(sq: SessionQuestion) -> datetime:
    """Bu andan sonra gelen cevap "süre doldu" sayılır (limit + ağ toleransı)."""
    return sq.served_at + _ms(time_limit_ms() + settings.QUIZ_LATENCY_GRACE_MS)


# --------------------------------------------------------------------------- soru seçimi


def playable_questions(category: Category):
    """Aktif, tam 4 şıklı ve tam 1 doğru şıklı sorular."""
    return (
        Question.objects.active()
        .filter(category=category)
        .annotate(
            n_choices=Count("choices"),
            n_correct=Count("choices", filter=Q(choices__is_correct=True)),
        )
        .filter(n_choices=4, n_correct=1)
    )


def pick_question_ids(category: Category, count: int | None = None) -> list[int]:
    """Zorluk dağılımına göre (8 kolay / 8 orta / 4 zor) rastgele soru seçer.

    Bir zorlukta yeterli soru yoksa eksikler kalan sorulardan tamamlanır.
    Sonuç karıştırılmış sırada döner.
    """
    count = count or questions_per_session()
    pool: dict[int, list[int]] = {}
    for qid, difficulty in playable_questions(category).values_list("id", "difficulty"):
        pool.setdefault(difficulty, []).append(qid)

    if sum(len(ids) for ids in pool.values()) < count:
        raise exc.NotEnoughQuestions()

    picked: list[int] = []
    for difficulty, need in settings.QUIZ_DIFFICULTY_MIX.items():
        ids = pool.get(difficulty, [])
        take = _rng.sample(ids, min(need, len(ids)))
        picked.extend(take)
    if len(picked) < count:
        remaining = [qid for ids in pool.values() for qid in ids if qid not in set(picked)]
        picked.extend(_rng.sample(remaining, count - len(picked)))
    picked = picked[:count]
    _rng.shuffle(picked)
    return picked


# --------------------------------------------------------------------------- oturum


@dataclass
class StartedSession:
    session: QuizSession
    token: str
    question: SessionQuestion


@transaction.atomic
def start_session(category_slug: str, client_type: str = "web") -> StartedSession:
    category = Category.objects.filter(slug=category_slug, is_active=True).first()
    if category is None:
        raise exc.CategoryNotFound()

    question_ids = pick_question_ids(category)
    choices_by_question: dict[int, list[int]] = {}
    for qid, cid in (
        Question.objects.filter(id__in=question_ids)
        .values_list("id", "choices__id")
        .order_by("id", "choices__id")
    ):
        choices_by_question.setdefault(qid, []).append(cid)

    now = timezone.now()
    token, token_hash = QuizSession.generate_token()
    session = QuizSession.objects.create(
        category=category, token_hash=token_hash, client_type=client_type, started_at=now
    )
    rows = []
    for order, qid in enumerate(question_ids, start=1):
        choice_order = list(choices_by_question[qid])
        _rng.shuffle(choice_order)
        rows.append(
            SessionQuestion(
                session=session,
                question_id=qid,
                order=order,
                choice_order=choice_order,
                served_at=now + _ms(settings.QUIZ_READY_COUNTDOWN_MS) if order == 1 else None,
            )
        )
    SessionQuestion.objects.bulk_create(rows)
    first = (
        SessionQuestion.objects.select_related("question")
        .prefetch_related("question__choices")
        .get(session=session, order=1)
    )
    return StartedSession(session=session, token=token, question=first)


def get_session(session_id, token: str | None, *, for_update: bool = False) -> QuizSession:
    """Oturumu getirir ve token'ı doğrular. `for_update` transaction içinde kullanılmalı."""
    qs = QuizSession.objects.select_related("category")
    if for_update:
        qs = qs.select_for_update(of=("self",))
    try:
        session = qs.get(pk=session_id)
    except (QuizSession.DoesNotExist, ValidationError, ValueError, TypeError) as e:
        raise exc.SessionNotFound() from e
    if not session.check_token(token):
        raise exc.InvalidSessionToken()
    return session


def _expire_if_stale(session: QuizSession, now: datetime) -> None:
    if session.status != QuizSession.Status.IN_PROGRESS:
        return
    limit = timedelta(minutes=settings.QUIZ_SESSION_EXPIRE_MINUTES)
    if now - session.started_at > limit:
        session.status = QuizSession.Status.EXPIRED
        session.save(update_fields=["status"])


def _current_sq(session: QuizSession) -> SessionQuestion | None:
    if session.current_index >= questions_per_session():
        return None
    return (
        SessionQuestion.objects.select_related("question")
        .prefetch_related("question__choices")
        .filter(session=session, order=session.current_index + 1)
        .first()
    )


def _record(
    session: QuizSession,
    sq: SessionQuestion,
    *,
    answered_at: datetime,
    selected_choice_id: int | None,
    is_correct: bool,
    timed_out: bool,
    response_ms: int,
    next_served_at: datetime,
) -> SessionQuestion | None:
    """Bir cevabı kaydeder, oturumu ilerletir; varsa sıradaki soruyu sunar."""
    points = calculate_points(is_correct, response_ms) if not timed_out else 0
    sq.answered_at = answered_at
    sq.selected_choice_id = selected_choice_id
    sq.is_correct = is_correct
    sq.timed_out = timed_out
    sq.response_ms = response_ms
    sq.points = points
    sq.save(
        update_fields=[
            "answered_at",
            "selected_choice",
            "is_correct",
            "timed_out",
            "response_ms",
            "points",
        ]
    )

    session.score += points
    session.correct_count += int(is_correct)
    session.total_time_ms += response_ms
    session.current_index += 1
    update = ["score", "correct_count", "total_time_ms", "current_index"]

    next_sq = None
    if session.current_index >= questions_per_session():
        session.status = QuizSession.Status.COMPLETED
        session.finished_at = answered_at
        update += ["status", "finished_at"]
    else:
        next_sq = SessionQuestion.objects.get(session=session, order=session.current_index + 1)
        next_sq.served_at = next_served_at
        next_sq.save(update_fields=["served_at"])
    session.save(update_fields=update)
    return next_sq


def _advance_overdue(session: QuizSession, now: datetime) -> None:
    """Cevap gelmeden süresi (tolerans dahil) dolan soruları "süre doldu" olarak kapatır."""
    limit = time_limit_ms()
    while session.status == QuizSession.Status.IN_PROGRESS:
        sq = _current_sq(session)
        if sq is None or sq.served_at is None or now <= answer_deadline(sq):
            return
        timeout_at = sq.served_at + _ms(limit)
        _record(
            session,
            sq,
            answered_at=timeout_at,
            selected_choice_id=None,
            is_correct=False,
            timed_out=True,
            response_ms=limit,
            next_served_at=timeout_at + _ms(settings.QUIZ_FEEDBACK_MS),
        )


def run_locked(session_id, token: str | None, fn):
    """Oturumu kilitler, günceller (zaman aşımı, süresi dolan sorular), `fn(session, now)` çağırır.

    Süresi dolmuş oturum "expired" olarak *kaydedilir* ve ardından `SessionExpired`
    fırlatılır (hata transaction dışında fırlatıldığı için durum değişikliği geri alınmaz).
    """
    now = timezone.now()
    with transaction.atomic():
        session = get_session(session_id, token, for_update=True)
        _expire_if_stale(session, now)
        if session.status != QuizSession.Status.EXPIRED:
            _advance_overdue(session, now)
            return fn(session, now)
    raise exc.SessionExpired()


# --------------------------------------------------------------------------- okuma


@dataclass
class SessionState:
    session: QuizSession
    question: SessionQuestion | None
    answers: list[SessionQuestion] = field(default_factory=list)

    @property
    def finished(self) -> bool:
        return self.session.status == QuizSession.Status.COMPLETED


def answered_questions(session: QuizSession) -> list[SessionQuestion]:
    return list(
        SessionQuestion.objects.filter(session=session, answered_at__isnull=False).order_by("order")
    )


def get_current(session_id, token: str | None) -> SessionState:
    """Yenileme/devam: o anki soruyu (süresi dolanları kapattıktan sonra) döner."""

    def _state(session, now):
        return SessionState(
            session=session, question=_current_sq(session), answers=answered_questions(session)
        )

    return run_locked(session_id, token, _state)


def get_result(session_id, token: str | None) -> SessionState:
    def _result(session, now):
        if session.status != QuizSession.Status.COMPLETED:
            raise exc.SessionNotFinished()
        return SessionState(session=session, question=None, answers=answered_questions(session))

    return run_locked(session_id, token, _result)


# --------------------------------------------------------------------------- cevap


@dataclass
class AnswerResult:
    session: QuizSession
    answered: SessionQuestion
    correct_choice_id: int
    next_question: SessionQuestion | None

    @property
    def finished(self) -> bool:
        return self.session.status == QuizSession.Status.COMPLETED


def public_choices(sq: SessionQuestion) -> list[dict]:
    """Şıkları karıştırılmış sırada, oturuma özel 1–4 kimlikleriyle döner (doğru bilgisi yok)."""
    by_id = {c.id: c for c in sq.question.choices.all()}
    return [
        {"id": key, "text": by_id[db_id].text}
        for key, db_id in enumerate(sq.choice_order, start=1)
        if db_id in by_id
    ]


def _db_choice_id(sq: SessionQuestion, key: int) -> int:
    if isinstance(key, bool) or not isinstance(key, int) or not 1 <= key <= len(sq.choice_order):
        raise exc.InvalidChoice()
    return sq.choice_order[key - 1]


def _public_choice_key(sq: SessionQuestion, db_id: int | None) -> int | None:
    if db_id is None or db_id not in sq.choice_order:
        return None
    return sq.choice_order.index(db_id) + 1


def correct_choice_id(sq: SessionQuestion) -> int:
    """Doğru şıkkın oturuma özel kimliği (1–4)."""
    db_id = next(c.id for c in sq.question.choices.all() if c.is_correct)
    return _public_choice_key(sq, db_id)


def selected_choice_key(sq: SessionQuestion) -> int | None:
    return _public_choice_key(sq, sq.selected_choice_id)


def _answer_result(session: QuizSession, sq: SessionQuestion) -> AnswerResult:
    sq = (
        SessionQuestion.objects.select_related("question")
        .prefetch_related("question__choices")
        .get(pk=sq.pk)
    )
    next_sq = None
    if sq.order < questions_per_session():
        next_sq = (
            SessionQuestion.objects.select_related("question")
            .prefetch_related("question__choices")
            .get(session=session, order=sq.order + 1)
        )
    return AnswerResult(
        session=session,
        answered=sq,
        correct_choice_id=correct_choice_id(sq),
        next_question=next_sq,
    )


def submit_answer(
    session_id, token: str | None, question_id: int, choice_id: int | None
) -> AnswerResult:
    """Cevabı (veya `choice_id=None` ile süre dolmasını) değerlendirir.

    - Aynı soruya ikinci cevap kabul edilmez; ilk sonuç tekrar döner (idempotent).
    - Güncel olmayan bir soru için 409 `question_mismatch`.
    - `choice_id` oturuma özel şık kimliğidir (1–4), bkz. modül açıklaması.
    """
    return run_locked(
        session_id, token, lambda session, now: _submit(session, now, question_id, choice_id)
    )


def _submit(session: QuizSession, now: datetime, question_id, choice_id) -> AnswerResult:
    sq = SessionQuestion.objects.filter(session=session, question_id=question_id).first()
    if sq is None:
        raise exc.QuestionMismatch()
    if sq.answered_at is not None:
        return _answer_result(session, sq)
    if session.status == QuizSession.Status.COMPLETED:
        raise exc.SessionFinished()
    if sq.order != session.current_index + 1:
        raise exc.QuestionMismatch()

    selected_db_id = _db_choice_id(sq, choice_id) if choice_id is not None else None

    limit = time_limit_ms()
    elapsed = max(_elapsed_ms(sq.served_at, now), 0)
    if choice_id is None or now > answer_deadline(sq):
        # İstemci sayacı doldu ya da cevap tolerans dışında geldi.
        is_correct, timed_out, response_ms, selected = False, True, limit, None
    else:
        correct_db_id = (
            Question.objects.get(pk=sq.question_id)
            .choices.filter(is_correct=True)
            .values_list("id", flat=True)
            .get()
        )
        is_correct = selected_db_id == correct_db_id
        timed_out, response_ms, selected = False, min(elapsed, limit), selected_db_id

    _record(
        session,
        sq,
        answered_at=now,
        selected_choice_id=selected,
        is_correct=is_correct,
        timed_out=timed_out,
        response_ms=response_ms,
        next_served_at=now + _ms(settings.QUIZ_FEEDBACK_MS),
    )
    return _answer_result(session, sq)


def remaining_ms(sq: SessionQuestion, now: datetime | None = None) -> int:
    """Sorunun kalan süresi; sayaç henüz başlamadıysa tam süre."""
    now = now or timezone.now()
    limit = time_limit_ms()
    if sq.served_at is None or now <= sq.served_at:
        return limit
    return max(limit - _elapsed_ms(sq.served_at, now), 0)


def starts_in_ms(sq: SessionQuestion, now: datetime | None = None) -> int:
    """Sayaç başlayana kadar beklenecek süre (3-2-1 sayımı / geri bildirim)."""
    now = now or timezone.now()
    if sq.served_at is None or now >= sq.served_at:
        return 0
    return _elapsed_ms(now, sq.served_at)
