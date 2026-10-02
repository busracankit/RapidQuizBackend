"""Ortak pytest fixture'ları ve küçük veri üreticileri."""

import pytest

from apps.quiz.models import Category, Choice, Question, QuizSession


@pytest.fixture(autouse=True)
def _clear_cache():
    """Throttle sayaçları testler arasında taşınmasın."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def category(db):
    # 0002_seed_categories migration'ı 5 kategoriyi oluşturur.
    return Category.objects.get(slug="yazilim")


def make_question(category, text="Python'da liste hangi parantezle yazılır?", correct=0, **kw):
    question = Question.objects.create(category=category, text=text, **kw)
    for i, label in enumerate(["[]", "()", "{}", "<>"]):
        Choice.objects.create(question=question, text=label, is_correct=(i == correct), order=i)
    return question


def fill_category(category, easy=10, medium=10, hard=5):
    """Kategoriye oynanabilir sorular ekler (zorluk başına verilen sayıda)."""
    created = []
    for difficulty, n in ((1, easy), (2, medium), (3, hard)):
        for i in range(n):
            created.append(
                make_question(category, text=f"Z{difficulty} soru {i}", difficulty=difficulty)
            )
    return created


@pytest.fixture
def full_category(category):
    fill_category(category)
    return category


@pytest.fixture
def question(category):
    return make_question(category)


def make_session(category, **kw):
    token, token_hash = QuizSession.generate_token()
    session = QuizSession.objects.create(category=category, token_hash=token_hash, **kw)
    session.plain_token = token
    return session


@pytest.fixture
def quiz_session(category):
    return make_session(category)
