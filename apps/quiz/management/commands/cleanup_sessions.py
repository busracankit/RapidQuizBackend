"""Yarım kalan oturumları kapatır ve eski tamamlanmamış oturumları siler.

DigitalOcean'da her gün 04:00 (Europe/Istanbul) SCHEDULED job olarak çalışır.
"""

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.quiz.models import QuizSession


class Command(BaseCommand):
    help = (
        "QUIZ_SESSION_EXPIRE_MINUTES'tan uzun süren oturumları 'expired' yapar; "
        "QUIZ_CLEANUP_DAYS'ten eski tamamlanmamış oturumları siler."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Değişiklik yapmadan say.")

    def handle(self, *args, dry_run: bool = False, **options):
        now = timezone.now()
        expire_before = now - timedelta(minutes=settings.QUIZ_SESSION_EXPIRE_MINUTES)
        delete_before = now - timedelta(days=settings.QUIZ_CLEANUP_DAYS)

        to_expire = QuizSession.objects.filter(
            status=QuizSession.Status.IN_PROGRESS, started_at__lt=expire_before
        )
        to_delete = QuizSession.objects.exclude(status=QuizSession.Status.COMPLETED).filter(
            started_at__lt=delete_before
        )

        if dry_run:
            self.stdout.write(
                f"[dry-run] kapatılacak: {to_expire.count()}, silinecek: {to_delete.count()}"
            )
            return

        expired = to_expire.update(status=QuizSession.Status.EXPIRED)
        deleted, _ = to_delete.delete()
        self.stdout.write(
            self.style.SUCCESS(f"Kapatılan oturum: {expired}, silinen kayıt: {deleted}")
        )
