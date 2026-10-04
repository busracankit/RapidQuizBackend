# Rapid Quiz — Backend (CLAUDE.md)

Rapid Quiz'in Django + DRF REST API'si. Web (Vue) ve mobil istemciler aynı `/api/v1/` API'sini kullanır.

- **Proje dokümanı (tek doğruluk kaynağı):** `docs/rapid-quiz-proje-dokumani.md`
- **Frontend reposu:** `../RapidQuizFrontend` (Vue 3 + Vite + TS). İki repo arasındaki tek sözleşme OpenAPI şemasıdır (`/api/schema/`).

## Git

- Remote: `origin` → https://github.com/busracankit/RapidQuizBackend.git (frontend: `RapidQuizFrontend.git`), dal `main`.
- `main`'e push → GitHub Actions CI (`.github/workflows/ci.yml`) ve DigitalOcean otomatik deploy.

## Deploy (DigitalOcean App Platform)

Backend + frontend **tek uygulama** (`.do/app.yaml`): `/api`, `/admin`, `/static` → `api` (Dockerfile), geri kalan
→ `web` (frontend reposundan statik site). Aynı köken → CORS yok. Managed PostgreSQL 18 kümesi `rapid-quiz-db`.
`migrate` PRE_DEPLOY job'ı `migrate && load_questions` çalıştırır. Adım adım kurulum: `docs/deploy.md`.
`DJANGO_SECRET_KEY` repoya yazılmaz (spec'te `__DJANGO_SECRET_KEY__` yer tutucusu).

## Teknoloji

Python 3.14 · Django 6.1.1 · DRF 3.18.1 · PostgreSQL 18 · psycopg 3 · drf-spectacular (+sidecar) · django-cors-headers ·
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
uv run manage.py load_questions [--check] [--deactivate-missing] [dosya.json ...]
uv run manage.py cleanup_sessions [--dry-run]
uv run manage.py spectacular --validate --fail-on-warn --file schema.yml   # OpenAPI
```

## Yapı

```
config/settings/{base,dev,prod,test}.py   # DJANGO_SETTINGS_MODULE; manage.py → dev, wsgi → prod, pytest → test
config/middleware.py                      # HealthCheckMiddleware: /api/v1/health/ (ALLOWED_HOSTS'tan önce)
config/api.py                             # sabit hata formatı (EXCEPTION_HANDLER) + /api/ altında JSON 404
config/urls.py                            # /api/v1/ rotaları, /api/schema/, /api/docs/ (Swagger, sidecar ile yerel)
apps/quiz/services.py      oyun kuralları: soru seçimi, oturum, cevap, süre, puan  ← iş kuralları BURADA
apps/quiz/exceptions.py    QuizError alt sınıfları (code + HTTP status)
apps/quiz/loaders.py       soru JSON doğrulama/yükleme (load_questions)
apps/quiz/serializers.py   istek/yanıt şemaları + *_payload() gövde üreticileri
apps/leaderboard/services.py  isim temizleme, skor kaydı, sıralama; profanity.py küfür filtresi
data/questions/<slug>.json    soru verisi (correct + 3 wrong, difficulty 1–3)
apps/conftest.py  fixture'lar: category, full_category, question, quiz_session; make_question(), fill_category(), make_session()
apps/api_tests/   uçtan uca API testleri
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
  Zorlukta eksik varsa oturum diğer zorluklardan tamamlar; toplam < 20 ise 409 `not_enough_questions`.
- **Şık kimlikleri (dokümandan sapma):** API'de `choices[].id`, `choice_id`, `correct_choice_id` oturuma özel
  **1–4** değerleridir (`SessionQuestion.choice_order` sırası + 1). DB id'leri gönderilmez, çünkü yükleyici doğru
  şıkkı ilk oluşturduğundan en küçük id doğru cevabı ele verirdi.
- **Süresi dolan sorular:** Sunucu, istemcinin yapacağını taklit eder: `served_at + 5750 ms` geçen soru
  "süre doldu" (5000 ms) kaydedilir, sonraki sorunun `served_at`'i `önceki served_at + 5000 + 800` olur. Bu her
  oturum erişiminde (`run_locked`) zincirleme uygulanır; uzun ayrılıkta oyun 0 puanla tamamlanır.
- **Zaman aşımı:** `started_at`'ten 30 dk sonra erişilen `in_progress` oturum `expired` yapılır → 410.
- **Erken cevap:** `served_at`'ten önce gelen cevap 0 ms sayılır (dürüst istemci soruyu `starts_in_ms` sonra gösterir).
- **Throttling:** `ScopedRateThrottle` (session_create 30/dk, answer 120/dk, score 10/dk, read 300/dk), IP bazlı;
  prod'da `NUM_PROXIES=1`. Cache varsayılan LocMem (worker başına) — çok instance'ta Redis gerekir.

## API v1 sözleşmesi (özet; tam şema `/api/schema/`)

| Metot | Yol | Başarı | Önemli hatalar |
| --- | --- | --- | --- |
| GET | `/api/v1/categories/` | 200 liste | — |
| POST | `/api/v1/sessions/` `{category, client_type}` | 201 `{session_id, session_token, category, total_questions, time_limit_ms, question}` | 400, 404 `category_not_found`, 409 `not_enough_questions`, 429 |
| GET | `/api/v1/sessions/{id}/current/` | 200 `{status, score, answered_count, finished, question\|null, answers[]}` | 403 `invalid_session_token`, 404, 410 `session_expired` |
| POST | `/api/v1/sessions/{id}/answers/` `{question_id, choice_id\|null}` | 200 `{is_correct, timed_out, correct_choice_id, selected_choice_id, points, score, correct_count, answered_count, finished, next_question\|null}` | 400, 403, 409 `question_mismatch`, 410 |
| GET | `/api/v1/sessions/{id}/result/` | 200 `{score, max_score, correct_count, total_time_ms, answers[], score_saved, player_name, rank}` | 409 `session_not_finished` |
| POST | `/api/v1/sessions/{id}/score/` `{player_name}` | 201 `{entry, rank, in_top, leaderboard}` | 400 `invalid_player_name`, 409 `score_already_saved`/`session_not_finished` |
| GET | `/api/v1/leaderboard/?category=slug` | 200 `{category, entries[{id, rank, player_name, score, correct_count, total_time_ms, created_at}]}` | 400, 404 |

Soru nesnesi: `{index, id, text, difficulty, choices[{id: 1–4, text}], served_at, starts_in_ms, remaining_ms}`.
İstemci `starts_in_ms` bekler (3-2-1 / geri bildirim), sonra `remaining_ms`'den geri sayar; süre dolunca `choice_id: null` gönderir.
Hata: `{"error": {"code", "message", "details"?}}`. Oturum header'ı: `X-Session-Token`.

## Yol haritası durumu (Faz 1)

- [x] Proje kurulumu (uv, bölünmüş ayarlar, docker-compose, Dockerfile, `.do/app.yaml`)
- [x] Modeller, migration'lar, admin (inline şıklar + doğrulama), `cleanup_sessions` komutu
- [x] `load_questions` komutu + 5×20 soruluk JSON (`data/questions/`)
- [x] Servis katmanı (oturum açma, cevap, süre toleransı, puan)
- [x] v1 endpointleri, hata formatı, throttling, CORS
- [x] drf-spectacular şeması + Swagger UI (`drf-spectacular-sidecar` ile CDN'siz)

Faz 1 tamam. Sırada Faz 2 (frontend, `../RapidQuizFrontend`). Faz 3'te: CI, deploy, soruları 60'a çıkarma.
