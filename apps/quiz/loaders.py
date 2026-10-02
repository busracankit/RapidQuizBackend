"""Soru JSON dosyalarını doğrular ve veritabanına yükler (`load_questions` komutu).

Dosya biçimi (`data/questions/<slug>.json`):

    {
      "category": {"slug": "yazilim", "name": "Yazılım", "description": "...",
                   "icon": "code", "color": "#3B82F6", "order": 1},
      "questions": [
        {"text": "...", "difficulty": 1, "correct": "doğru şık",
         "wrong": ["yanlış 1", "yanlış 2", "yanlış 3"], "explanation": "..."}
      ]
    }

Yükleme idempotenttir: sorular (kategori, metin) ile eşleşir; var olan soru ve
şıkları yerinde güncellenir (oynanmış şıklar silinmez).
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from django.db import transaction

from .models import (
    CHOICE_TEXT_MAX_LENGTH,
    CHOICES_PER_QUESTION,
    QUESTION_TEXT_MAX_LENGTH,
    Category,
    Choice,
    Question,
)

HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
CATEGORY_FIELDS = ("name", "description", "icon", "color", "order")


class QuestionFileError(Exception):
    """Dosya doğrulanamadı; `errors` tüm hataları içerir."""

    def __init__(self, path, errors):
        self.path = path
        self.errors = errors
        super().__init__(f"{path}: {len(errors)} hata")


@dataclass
class LoadResult:
    category: str
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    deactivated: int = 0
    difficulty_counts: dict = field(default_factory=dict)


def _norm(text: str) -> str:
    return " ".join(text.split()).casefold()


def validate_payload(data) -> list[str]:
    """Dosya içeriğini doğrular, hata mesajlarını döner (boş liste = geçerli)."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["Kök öğe bir JSON nesnesi olmalı."]

    cat = data.get("category")
    if not isinstance(cat, dict):
        errors.append("'category' nesnesi eksik.")
    else:
        if not cat.get("slug"):
            errors.append("category.slug zorunlu.")
        if not cat.get("name"):
            errors.append("category.name zorunlu.")
        if "color" in cat and not HEX_COLOR.match(str(cat["color"])):
            errors.append("category.color #RRGGBB biçiminde olmalı.")

    questions = data.get("questions")
    if not isinstance(questions, list) or not questions:
        errors.append("'questions' boş olmayan bir liste olmalı.")
        return errors

    seen: set[str] = set()
    for i, q in enumerate(questions, start=1):
        p = f"Soru {i}"
        if not isinstance(q, dict):
            errors.append(f"{p}: nesne olmalı.")
            continue
        text = (q.get("text") or "").strip()
        if not text:
            errors.append(f"{p}: 'text' zorunlu.")
        elif len(text) > QUESTION_TEXT_MAX_LENGTH:
            errors.append(f"{p}: metin {len(text)} karakter (en fazla {QUESTION_TEXT_MAX_LENGTH}).")
        if text and _norm(text) in seen:
            errors.append(f"{p}: aynı soru dosyada birden fazla kez var.")
        seen.add(_norm(text))

        if q.get("difficulty") not in (1, 2, 3):
            errors.append(f"{p}: 'difficulty' 1, 2 veya 3 olmalı.")

        correct = q.get("correct")
        wrong = q.get("wrong")
        if not isinstance(correct, str) or not correct.strip():
            errors.append(f"{p}: 'correct' zorunlu.")
            correct = ""
        if not isinstance(wrong, list) or len(wrong) != CHOICES_PER_QUESTION - 1:
            errors.append(f"{p}: 'wrong' tam {CHOICES_PER_QUESTION - 1} şık içermeli.")
            wrong = []
        choices = [correct, *wrong]
        for c in choices:
            if not isinstance(c, str) or not c.strip():
                errors.append(f"{p}: boş şık var.")
            elif len(c.strip()) > CHOICE_TEXT_MAX_LENGTH:
                errors.append(
                    f"{p}: '{c}' {len(c.strip())} karakter (en fazla {CHOICE_TEXT_MAX_LENGTH})."
                )
        normed = [_norm(c) for c in choices if isinstance(c, str)]
        if len(set(normed)) != len(normed):
            errors.append(f"{p}: şık metinleri birbirinden farklı olmalı.")
    return errors


def read_question_file(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise QuestionFileError(path, [f"Geçersiz JSON: {exc}"]) from exc
    errors = validate_payload(data)
    if errors:
        raise QuestionFileError(path, errors)
    return data


def _sync_choices(question: Question, correct: str, wrong: list[str]) -> bool:
    """Şıkları yerinde günceller; değişiklik olduysa True döner."""
    desired = [(correct.strip(), True)] + [(w.strip(), False) for w in wrong]
    existing = list(question.choices.order_by("order", "id"))
    current = [(c.text, c.is_correct) for c in existing]
    if current == desired:
        return False

    # Oynanmış şıklar PROTECT ile korunduğundan silmek yerine yerinde güncellenir.
    # "Tek doğru şık" kısıtına takılmamak için önce hepsi yanlış yapılır.
    Choice.objects.filter(question=question).update(is_correct=False)
    for order, (text, _is_correct) in enumerate(desired):
        if order < len(existing):
            choice = existing[order]
            choice.text, choice.order = text, order
            choice.is_correct = False
            choice.save(update_fields=["text", "order", "is_correct"])
        else:
            existing.append(Choice.objects.create(question=question, text=text, order=order))
    for extra in existing[len(desired) :]:
        extra.delete()
    correct_choice = existing[0]
    correct_choice.is_correct = True
    correct_choice.save(update_fields=["is_correct"])
    return True


@transaction.atomic
def load_payload(data: dict, *, deactivate_missing: bool = False) -> LoadResult:
    cat_data = data["category"]
    defaults = {k: cat_data[k] for k in CATEGORY_FIELDS if k in cat_data}
    category, _ = Category.objects.update_or_create(slug=cat_data["slug"], defaults=defaults)
    result = LoadResult(category=category.slug)

    existing = {_norm(q.text): q for q in category.questions.all()}
    loaded_ids: set[int] = set()

    for item in data["questions"]:
        text = item["text"].strip()
        fields = {
            "difficulty": item["difficulty"],
            "explanation": (item.get("explanation") or "").strip(),
            "is_active": item.get("is_active", True),
        }
        result.difficulty_counts[item["difficulty"]] = (
            result.difficulty_counts.get(item["difficulty"], 0) + 1
        )
        question = existing.get(_norm(text))
        if question is None:
            question = Question.objects.create(category=category, text=text, **fields)
            _sync_choices(question, item["correct"], item["wrong"])
            result.created += 1
        else:
            changed = question.text != text or any(
                getattr(question, k) != v for k, v in fields.items()
            )
            if changed:
                question.text = text
                for k, v in fields.items():
                    setattr(question, k, v)
                question.save()
            choices_changed = _sync_choices(question, item["correct"], item["wrong"])
            if changed or choices_changed:
                result.updated += 1
            else:
                result.unchanged += 1
        loaded_ids.add(question.id)

    if deactivate_missing:
        result.deactivated = (
            category.questions.filter(is_active=True)
            .exclude(id__in=loaded_ids)
            .update(is_active=False)
        )
    return result
