# Rapid Quiz — Backend (CLAUDE.md)

Rapid Quiz'in Django + DRF REST API'si. Web (Vue) ve mobil istemciler aynı `/api/v1/` API'sini kullanır.

- **Proje dokümanı (tek doğruluk kaynağı):** `docs/rapid-quiz-proje-dokumani.md`
- **Frontend reposu:** `../RapidQuizFrontend` (Vue 3 + Vite + TS). İki repo arasındaki tek sözleşme OpenAPI şemasıdır (`/api/schema/`).

## Teknoloji

Python 3.14 · Django 6.1.1 · DRF 3.18.1 · PostgreSQL 18 · psycopg 3 · drf-spectacular · django-cors-headers ·
django-environ · gunicorn · WhiteNoise · pytest-django · ruff · uv. Sürümler `pyproject.toml` + `uv.lock` ile sabit.

## Komutlar

```bash
docker compose up -d db                 # yerel PostgreSQL 18
cp .env.example .env                    # ilk seferde
uv sync                                 # bağımlılıklar (.venv)
uv run manage.py migrate                # 5 kategori migration ile gelir
uv run manage.py createsuperuser
uv run manage.py runserver              # http://localhost:8000  (admin: /admin/, API docs: /api/docs/)
uv run pytest                           # testler (PostgreSQL gerekir, config.settings.test)
uv run pytest --cov                     # kapsama
uv run ruff format . && uv run ruff check .
uv run manage.py cleanup_sessions [--dry-run]
```

## Yapı

```
config/settings/{base,dev,prod,test}.py   # DJANGO_SETTINGS_MODULE; manage.py → dev, wsgi → prod, pytest → test
config/middleware.py                      # HealthCheckMiddleware: /api/v1/health/ (ALLOWED_HOSTS'tan önce)
apps/quiz/        Category, Question, Choice, QuizSession, SessionQuestion + admin + komutlar
apps/leaderboard/ LeaderboardEntry (+ ranked(), top_for_category())
apps/conftest.py  ortak fixture'lar: category, question, quiz_session, make_question(), make_session()
```

## Kurallar

- **İş kuralları yalnızca servis katmanında** (`apps/quiz/services.py`): süre, puan, sıralama. View'lar ince kalır; istemci yalnızca gösterir.
- **Önce test:** servis katmanı için testler önce yazılır; hedef %90+ kapsama. Testler PostgreSQL'de çalışır (partial unique constraint vb. gerçek DB davranışı).
- Zaman her yerde UTC ve sunucu saati; `timezone.now()` kullan. Testlerde zaman `time-machine` ile dondurulur.
- API'de cookie/CSRF yok; oturum `X-Session-Token` header'ı ile taşınır. Token DB'de yalnızca SHA-256 hash olarak (`QuizSession.generate_token()`/`check_token()`).
- Hata formatı: `{"error": {"code": "...", "message": "..."}}`. Doğru şık bilgisi soru ile asla gönderilmez.
- Migration'lar elle düzenlenmez (veri migration'ları hariç); model değişince `makemigrations`.
- Kod yorumları ve kullanıcıya dönük metinler Türkçe; kod isimleri İngilizce.

## Kararlar (dokümana ek, 2 Ekim 2026)

- **Süre başlangıcı:** Sunucu `served_at`'i ileri tarihler — ilk soruda `now + QUIZ_READY_COUNTDOWN_MS` (3000, 3-2-1 sayımı),
  sonraki sorularda `now + QUIZ_FEEDBACK_MS` (800, doğru/yanlış geri bildirimi). Böylece oyuncu tam 5 sn alır, ek istek gerekmez.
- **Yenilemede süresi geçmiş soru:** `/current/` çağrıldığında süresi (5000 + 750 ms tolerans) dolmuş sorular
  "süre doldu" sayılır ve sıradaki soru verilir.
- **Toplam süre (`total_time_ms`):** her sorunun `response_ms` toplamı; süre dolan sorular 5000 ms sayılır.
- **Skor tablosu:** yalnızca kategori bazlı Top 10; aynı isim birden fazla kez yer alabilir (her oyun ayrı satır).
- **Doğru şık değiştirme (admin):** Kısıt `choice_single_correct_per_question` partial unique index'tir (deferrable olamaz).
  Admin, kayıt sırasını "önce silinenler → is_correct=False → doğru şık" yapar; tek-form kısıt kontrolü kapalıdır,
  kural formset seviyesinde (tam 4 şık, tam 1 doğru, farklı metinler) doğrulanır.
- **Sorular:** Faz 1'de kategori başına 20 soru (8 kolay / 8 orta / 4 zor); soru ≤120, şık ≤40 karakter.

## Yol haritası durumu (Faz 1)

- [x] Proje kurulumu (uv, bölünmüş ayarlar, docker-compose, Dockerfile, `.do/app.yaml`)
- [x] Modeller, migration'lar, admin (inline şıklar + doğrulama), `cleanup_sessions` komutu
- [ ] `load_questions` komutu + 5×20 soruluk JSON (`data/questions/`)
- [ ] Servis katmanı (oturum açma, cevap, süre toleransı, puan) — önce testler
- [ ] v1 endpointleri, hata formatı, throttling, CORS
- [ ] drf-spectacular şeması; Swagger UI statiklerini kendimiz sunmak için `drf-spectacular-sidecar` değerlendirilecek
