# Rapid Quiz — Backend (CLAUDE.md)

Rapid Quiz'in Django + DRF REST API'si. Web (Vue) ve mobil istemciler aynı `/api/v1/` API'sini kullanır.

- **Proje dokümanı (tek doğruluk kaynağı):** `docs/rapid-quiz-proje-dokumani.md`
- **Frontend reposu:** `../RapidQuizFrontend` (Vue 3 + Vite + TS). İki repo arasındaki tek sözleşme OpenAPI şemasıdır (`/api/schema/`).

## Git

- Remote: `origin` → https://github.com/busracankit/RapidQuizBackend.git (frontend: `RapidQuizFrontend.git`), dal `main`.
- `main`'e push → GitHub Actions CI (`.github/workflows/ci.yml`) ve DigitalOcean otomatik deploy.

## Durum (5 Ekim 2026)

Faz 1, 2 ve 3 tamam. **Canlıya alındı** (DO panelinden manuel): `https://starfish-app-yuzxi.ondigitalocean.app`
(öğrenme amaçlı; kaynaklar maliyet nedeniyle silinebilir — silindiyse yeniden kurulum için `docs/deploy.md` ›
"Panelden kurulum"). Backend ve frontend CI'ı yeşil. Sıradaki: Faz 4 (mobil, iOS/Android).
Commit yazarı `Büşra Cankit <cankitbusra@gmail.com>` (geçmiş bu kimliğe göre yeniden yazıldı).

## Deploy — panelden kurulumda öğrenilenler (5 Ekim 2026)

Gerçek kurulum DO panelinden (doctl'siz) yapıldı ve çalıştı. Uygulama adı `starfish-app` (DO'nun verdiği ad),
adres `https://starfish-app-yuzxi.ondigitalocean.app` (**yuzxi** — içinde x var), bölge FRA1, veritabanı kümesi
`db-pgsql-rapidquiz`. Bileşenler: `api` (Dockerfile), frontend statik sitesi, `migrate` ve `cleanup-sessions` job'ları.

1. İki repoyu push et, GitHub Actions yeşil olsun. DO'ya GitHub yetkisini iki repo için ver.
2. Managed PostgreSQL oluştur (Databases › Create) ya da mevcut olanı kullan.
3. Apps › Create App › backend repo (`main`) → Dockerfile algılanır. HTTP port `8080`, health check `/api/v1/health/`.
4. **Ortam değişkenleri** (kritik; eksikse gunicorn worker'ı açılışta ölür):
   - App seviyesi: `DJANGO_SECRET_KEY` (**Encrypt**, `python3 -c "import secrets; print(secrets.token_urlsafe(50))"`
     ile üret, repoya yazma), `DJANGO_SETTINGS_MODULE=config.settings.prod`.
   - `api` bileşeni: `DATABASE_URL`, `DJANGO_ALLOWED_HOSTS=<alan adı, https:// olmadan>`,
     `CSRF_TRUSTED_ORIGINS=https://<alan adı>`, `WEB_CONCURRENCY=3`.
   - `DATABASE_URL` değerini elle yazma: önce veritabanını app'e **Add Resource › Database** ile ekle, sonra değer
     kutusuna `${` yaz, açılan listeden veritabanı bileşenini seç, `.` yazıp `DATABASE_URL`'yi seç →
     `${db-pgsql-rapidquiz.DATABASE_URL}`. Veritabanı app'e eklenmeden bu ifade "not a valid variable" der.
   - `${APP_DOMAIN}` app seviyesinde geçersizdir; alan adını doğrudan yazmak daha güvenli.
   - Frontend'e **hiçbir** ortam değişkeni verme (`VITE_API_BASE_URL` boş kalmalı → istemci `/api/v1`'e gider).
5. Frontend: Add components › Create resources from source code › frontend repo → Static Site, build
   `npm ci && npm run build`, output directory `dist`, route `/`. Sonra Settings › static site › **Custom Pages ›
   Catchall = `index.html`** (Vue Router history; yoksa alt sayfalarda yenileyince 404).
6. **Route'lar** (Settings › Routing): `api` için `/api`, `/admin`, `/static`; üçünde de **Preserve Full Path**.
   **Trim Prefix seçilirse** Django `/v1/categories/` görür ve düz "Not Found" döner (en sık hata). `/` frontend'de.
7. Job'lar (Add components › Create resources from source code › backend repo › Resource type **Job**):
   `migrate` (trigger: before every deployment) →
   `sh -c "python manage.py migrate --noinput && python manage.py load_questions"`;
   `cleanup-sessions` (trigger: On a schedule, `0 4 * * *`, Europe/Istanbul) → `python manage.py cleanup_sessions`.
   Her job'a `DATABASE_URL` aynı `${…}` önerisiyle verilir.
8. Doğrulama: `/api/v1/health/` → `{"status":"ok"}`, `/api/v1/categories/` → 5 kategori, ana sayfa, bir tam oyun,
   skor kaydı + skor tablosu, `/admin/` (CSS'li açılmalı). `createsuperuser` için `api` Console'u kullanılır.

**Sık hatalar:** `KeyError: 'DJANGO_SECRET_KEY'` / `Set the DATABASE_URL` → değişken ilgili bileşene ulaşmıyor;
`Bad Request (400)` → `DJANGO_ALLOWED_HOSTS` yanlış (yazım!); `Not Found` (Django) → Trim Prefix;
`Kategoriler yüklenemedi` → `/api` route'u backend'e gitmiyor. Tarayıcıda API JSON'u Safari'de bozuk harfli görünür
(charset başlığı yok); uygulama içinde (axios) sorun yoktur.

**Maliyet:** kaynaklar açık kaldığı sürece saatlik faturalanır, trafikten bağımsız: `api` (1 vCPU/1 GB) ~12 $/ay,
Managed PostgreSQL ~15 $/ay, statik site ücretsiz → ~1 $/gün. **Silmek için** uygulamayı (Apps › Destroy) **ve ayrıca**
veritabanını (Databases › Destroy) sil; veritabanı ayrı bir kaynaktır.

## Deploy (DigitalOcean App Platform)

Backend + frontend **tek uygulama** (`.do/app.yaml`): `/api`, `/admin`, `/static` → `api` (Dockerfile), geri kalan
→ `web` (frontend reposundan statik site). Aynı köken → CORS yok. Managed PostgreSQL 18 kümesi `rapid-quiz-db`.
`migrate` PRE_DEPLOY job'ı `migrate && load_questions` çalıştırır. Adım adım kurulum: `docs/deploy.md`.
`DJANGO_SECRET_KEY` repoya yazılmaz (spec'te `__DJANGO_SECRET_KEY__` yer tutucusu; panelde "Encrypt" işaretli env).

Panelde kurarken spec'teki değerler birebir kullanılır: `api` (Dockerfile, port 8080, health `/api/v1/health/`,
route'lar `/api` `/admin` `/static` + preserve path prefix), `web` statik site (`npm ci && npm run build`, `dist`,
catchall `index.html`, route `/`), `migrate` (Before every deploy), `cleanup-sessions` (Scheduled, `0 4 * * *`,
Europe/Istanbul), DB `rapid-quiz-db` (PG 18, fra1) + Trusted Sources, env'ler: `DJANGO_SETTINGS_MODULE`,
`DJANGO_SECRET_KEY`, `DATABASE_URL=${db.DATABASE_URL}`, `DJANGO_ALLOWED_HOSTS=${APP_DOMAIN}`,
`CSRF_TRUSTED_ORIGINS=https://${APP_DOMAIN}`, `WEB_CONCURRENCY=3`.

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
- **Sorular:** kategori başına 60 soru (24 kolay / 24 orta / 12 zor; Faz 3'te 20'den çıkarıldı); soru ≤120, şık ≤40 karakter.
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

Faz 1, 2 ve 3 tamam (CI, DigitalOcean yayını, 5×60 soru). Bkz. `docs/deploy.md` › Panelden kurulum.
