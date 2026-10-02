"""`data/questions/*.json` dosyalarındaki kategori ve soruları yükler.

uv run manage.py load_questions                    # tüm dosyalar
uv run manage.py load_questions data/questions/fizik.json
uv run manage.py load_questions --check            # yalnızca doğrula
uv run manage.py load_questions --deactivate-missing
"""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.quiz.loaders import QuestionFileError, load_payload, read_question_file

DEFAULT_DIR = Path(settings.BASE_DIR) / "data" / "questions"


class Command(BaseCommand):
    help = "Soru JSON dosyalarını doğrular ve veritabanına yükler (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "paths", nargs="*", help="JSON dosyaları (varsayılan: data/questions/*.json)"
        )
        parser.add_argument("--check", action="store_true", help="Yalnızca doğrula, yükleme.")
        parser.add_argument(
            "--deactivate-missing",
            action="store_true",
            help="Dosyada olmayan aktif soruları pasifleştir.",
        )

    def handle(self, *args, paths, check, deactivate_missing, **options):
        files = [Path(p) for p in paths] or sorted(DEFAULT_DIR.glob("*.json"))
        if not files:
            raise CommandError(f"Soru dosyası bulunamadı: {DEFAULT_DIR}")

        # Önce tüm dosyalar doğrulanır; tek bir hata varsa hiçbir şey yüklenmez.
        payloads, failed = [], False
        for path in files:
            if not path.exists():
                raise CommandError(f"Dosya yok: {path}")
            try:
                payloads.append((path, read_question_file(path)))
            except QuestionFileError as exc:
                failed = True
                self.stderr.write(self.style.ERROR(f"{path.name}:"))
                for err in exc.errors:
                    self.stderr.write(f"  - {err}")
        if failed:
            raise CommandError("Doğrulama başarısız; hiçbir soru yüklenmedi.")

        if check:
            total = sum(len(d["questions"]) for _, d in payloads)
            self.stdout.write(self.style.SUCCESS(f"{len(payloads)} dosya, {total} soru geçerli."))
            return

        mix = settings.QUIZ_DIFFICULTY_MIX
        for path, data in payloads:
            r = load_payload(data, deactivate_missing=deactivate_missing)
            counts = ", ".join(f"z{d}={r.difficulty_counts.get(d, 0)}" for d in (1, 2, 3))
            self.stdout.write(
                f"{r.category}: +{r.created} yeni, ~{r.updated} güncellendi, "
                f"={r.unchanged} aynı, -{r.deactivated} pasif ({counts})"
            )
            short = [d for d, need in mix.items() if r.difficulty_counts.get(d, 0) < need]
            if short:
                self.stdout.write(
                    self.style.WARNING(
                        f"  uyarı: {path.name} zorluk dağılımı hedefin altında "
                        f"(hedef {mix}); oturumlar eksikleri diğer zorluklardan tamamlar."
                    )
                )
        self.stdout.write(self.style.SUCCESS("Sorular yüklendi."))
