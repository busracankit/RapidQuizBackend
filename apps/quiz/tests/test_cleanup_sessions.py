from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.conftest import make_session
from apps.quiz.models import QuizSession

pytestmark = pytest.mark.django_db


def _run(*args):
    out = StringIO()
    call_command("cleanup_sessions", *args, stdout=out)
    return out.getvalue()


def test_expires_stale_in_progress_sessions(category):
    now = timezone.now()
    stale = make_session(category, started_at=now - timedelta(minutes=31))
    fresh = make_session(category, started_at=now - timedelta(minutes=5))

    _run()

    stale.refresh_from_db()
    fresh.refresh_from_db()
    assert stale.status == QuizSession.Status.EXPIRED
    assert fresh.status == QuizSession.Status.IN_PROGRESS


def test_deletes_old_unfinished_but_keeps_completed(category):
    old = timezone.now() - timedelta(days=31)
    old_expired = make_session(category, started_at=old, status=QuizSession.Status.EXPIRED)
    old_in_progress = make_session(category, started_at=old)
    old_completed = make_session(category, started_at=old, status=QuizSession.Status.COMPLETED)

    _run()

    remaining = set(QuizSession.objects.values_list("id", flat=True))
    assert old_expired.id not in remaining
    assert old_in_progress.id not in remaining
    assert old_completed.id in remaining


def test_dry_run_changes_nothing(category):
    s = make_session(category, started_at=timezone.now() - timedelta(days=40))
    output = _run("--dry-run")
    s.refresh_from_db()
    assert s.status == QuizSession.Status.IN_PROGRESS
    assert "silinecek: 1" in output
