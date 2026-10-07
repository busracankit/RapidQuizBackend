[🇬🇧 English](README.md) | 🇹🇷 Türkçe

# Rapid Quiz — Backend API

Hızlı bir bilgi yarışmasının REST API'si: **20 soru, her soru için 5 saniye, üyelik yok** ve **kategori bazlı İlk 10 skor tablosu**. Puanlama, süre ölçümü ve cevap kontrolü tamamen sunucuda yapılır.

> **Rapid Quiz'in bir parçası**
>
> | Repo | Rolü |
> | --- | --- |
> | [RapidQuizBackend](https://github.com/busracankit/RapidQuizBackend) | Django REST API: oyun mantığı, puanlama, skor tabloları (bu repo) |
> | [RapidQuizFrontend](https://github.com/busracankit/RapidQuizFrontend) | Web istemcisi (Vue 3 + TypeScript) |
> | [RapidQuizAndroid](https://github.com/busracankit/RapidQuizAndroid) | Android istemcisi (Kotlin + Jetpack Compose) |
>
> Canlı bir sunucu yok. Uygulama test amacıyla bir kez DigitalOcean App Platform'a kuruldu, ardından kapatıldı. Her şey aşağıdaki adımlarla yerelde çalışır.

## Özellikler

- 5 kategori ve 300 soru (her birinde 60: 24 kolay, 24 orta, 12 zor). Her oyun 20 rastgele soru seçer (8 kolay, 8 orta, 4 zor) ve şıkların sırasını karıştırır.
- Her soru için 5 saniyelik süre sınırı vardır ve bunu sunucu uygular. Hızlı doğru cevap daha çok puan getirir (soru başı 100–150).
- Üyeliksiz oyun: oyuncu yalnızca oyun sonunda skorunu kaydetmek için ismini yazar.
- Kategori başına İlk 10 skor tablosu. Oyuncu ilk 10'a giremese de kendi sırasını görür.
- Küfür filtresiyle isim doğrulama.
- Kategorileri, soruları ve skor kayıtlarını yönetmek için Django admin.
- Swagger arayüzlü OpenAPI 3 şeması: web ve mobil istemciler için tek ortak sözleşme.

## Teknolojiler

| Alan | Araçlar |
| --- | --- |
| Dil ve çatı | Python 3.14, Django 6.1, Django REST Framework 3.18 |
| Veritabanı | PostgreSQL 18 (psycopg 3) |
| API dokümanı | drf-spectacular (OpenAPI 3 + Swagger UI, sidecar ile yerelden sunulur) |
| Yapılandırma ve sunum | django-environ, django-cors-headers, gunicorn, WhiteNoise |
| Araçlar | uv (bağımlılıklar ve kilit dosyası), Ruff (lint ve biçimlendirme) |
| Test | pytest, pytest-django, pytest-cov, time-machine |
| Altyapı | Docker (çok aşamalı imaj), Docker Compose (yerel PostgreSQL), GitHub Actions CI |

## Mimari ve önemli tasarım kararları

- **Doğruluk kaynağı sunucudur.** Sorular doğru cevap olmadan gönderilir. Doğru şık yalnızca cevap yanıtında açıklanır. Puan, cevap süresi ve doğruluk servis katmanında (`apps/quiz/services.py`) hesaplanır. View'lar ince kalır, istemciler yalnızca sonucu gösterir.
- **Oturuma özel şık kimlikleri.** Şıklar veritabanı kimlikleriyle değil, oturuma özel karıştırılmış sırada `1–4` kimlikleriyle gönderilir. Yükleyici doğru şıkkı her zaman ilk oluşturduğu için veritabanı kimlikleri cevabı ele verirdi.
- **Durumsuz, cookie'siz oturum.** Oyun başlarken bir kez `session_token` döner, istemci bunu `X-Session-Token` başlığında gönderir. Cookie olmadığı için CSRF gerekmez ve mobil istemciler değişiklik olmadan çalışır. Veritabanında token'ın yalnızca SHA-256 hash'i tutulur.
- **Ağ toleranslı, sunucu tarafı zamanlama.** Her sorunun bir sunucu zaman damgası (`served_at`) vardır ve biraz ileri tarihlenir: ilk soruda 3-2-1 sayımı için +3 sn, sonrakilerde cevap geri bildirimi için +0,8 sn. İstemciler `starts_in_ms` ve `remaining_ms` alır, bu yüzden cihaz saatine hiç bağlı kalmaz. Cevaplar 5000 ms + 750 ms gecikme toleransına kadar kabul edilir. Süresi dolan sorular bir sonraki istekte otomatik kapanır, oyunlar 30 dakika sonra sona erer (`410`).
- **Puan formülü.** Doğru cevap `100 + floor(50 × (5000 − cevap_ms) / 5000)` puandır, yani soru başı 100–150, oyun başı en fazla 3000. Yanlış ya da süresi dolan cevap 0 puandır. Skor tablosunda eşitlik önce toplam süreye, sonra kayıt zamanına göre bozulur.
- **Eşzamanlılık güvenliği.** Her durum değişikliği oturum satırında `SELECT … FOR UPDATE` ile bir transaction içinde çalışır. Böylece aynı cevabın iki kez gönderilmesi yarış durumuna yol açmaz.
- **Oran sınırlama.** IP başına DRF scoped throttle'ları (dakikada): oyun başlatma 30, cevap 120, skor kaydı 10, okuma 300. Limitler ortam değişkenleriyle ayarlanabilir.
- **Tutarlı hata biçimi.** Doğrulama, 404 ve oran sınırı hataları dahil her hata `{"error": {"code": "...", "message": "...", "details": {...}}}` biçimindedir. Kodlar `session_expired`, `question_mismatch` gibi sabit ve makine tarafından okunabilir değerlerdir.
- **İşletim ayrıntıları.**
  - Sağlık kontrolü (`/api/v1/health/`) `SELECT 1` çalıştırır ve host doğrulamasından önce yanıtlanır.
  - Kategoriler bir veri migration'ı ile eklenir.
  - Soru dosyalarını doğrulayıp yükleyen, tekrar çalıştırılabilen bir `load_questions` komutu vardır, `--check` moduyla yalnızca doğrulama da yapabilir.
  - Eski oturumları kapatıp silen bir `cleanup_sessions` komutu vardır.
  - Ayarlar `base` / `dev` / `test` / `prod` olarak ayrılmıştır.
- **Testler.** Gerçek PostgreSQL üzerinde çalışan 223 test var, `apps/` kapsaması yaklaşık %98. Testlerde zaman time-machine ile dondurulur. CI sırasıyla Ruff, eksik migration kontrolü, soru dosyası doğrulaması, OpenAPI şema doğrulaması, test paketi ve Docker build çalıştırır.

## API özeti

Tüm uç noktalar `/api/v1/` altındadır. Oturum uç noktaları `X-Session-Token` başlığı ister.

| Metot | Yol | Açıklama |
| --- | --- | --- |
| `GET` | `/api/v1/health/` | Sağlık kontrolü (`{"status": "ok"}`) |
| `GET` | `/api/v1/categories/` | Aktif kategoriler |
| `POST` | `/api/v1/sessions/` | Oyunu başlatır (`{"category": "<slug>", "client_type": "web\|ios\|android"}`), token'ı ve ilk soruyu döner |
| `GET` | `/api/v1/sessions/{id}/current/` | Güncel oyun durumu (sayfa yenilemede ya da uygulamaya dönüşte senkron için) |
| `POST` | `/api/v1/sessions/{id}/answers/` | Cevap gönderir (süre dolduysa `choice_id: null`), sonucu ve sıradaki soruyu döner |
| `GET` | `/api/v1/sessions/{id}/result/` | Son puan, doğru sayısı ve toplam süre |
| `POST` | `/api/v1/sessions/{id}/score/` | Skoru oyuncu ismiyle kaydeder (oyun başına bir kez) |
| `GET` | `/api/v1/leaderboard/?category=<slug>` | Kategorinin İlk 10 listesi |

Etkileşimli doküman **`/api/docs/`** adresinde (Swagger UI), ham şema `/api/schema/` adresinde. Admin paneli `/admin/` adresinde.

## Kurulum ve çalıştırma

**Gerekenler:** [Docker](https://www.docker.com/) (PostgreSQL için) ve [uv](https://docs.astral.sh/uv/). Python 3.14 yoksa uv onu kendisi kurar.

```bash
git clone https://github.com/busracankit/RapidQuizBackend.git
cd RapidQuizBackend

cp .env.example .env               # yerel varsayılanlar; kendi DJANGO_SECRET_KEY değerini yaz
docker compose up -d db            # localhost:5432'de PostgreSQL 18
uv sync                            # bağımlılıkları .venv'e kurar
uv run manage.py migrate           # tabloları oluşturur ve 5 kategoriyi ekler
uv run manage.py load_questions    # data/questions/ altındaki 300 soruyu yükler
uv run manage.py createsuperuser   # isteğe bağlı: /admin/ için hesap
uv run manage.py runserver 0.0.0.0:8000
```

Çalıştığını kontrol et:

```bash
curl http://localhost:8000/api/v1/health/
# {"status":"ok"}
```

**Android emülatörü:** emülatör bilgisayarına `10.0.2.2` adresiyle ulaşır, bu yüzden bu adresi `.env` içindeki `DJANGO_ALLOWED_HOSTS` değerine ekle. Eklemezsen Django `400 Bad Request` döner:

```
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0,10.0.2.2
```

**Web istemcisi:** [frontend](https://github.com/busracankit/RapidQuizFrontend) geliştirme sunucusu `http://localhost:5173` adresinde çalışır. Bu adrese `CORS_ALLOWED_ORIGINS` içinde zaten izin verilmiştir.

## Testleri çalıştırma

Testler bir önceki adımdaki PostgreSQL konteynerine ihtiyaç duyar (`docker compose up -d db`).

```bash
uv run pytest                      # 223 test
uv run pytest --cov                # kapsama raporuyla
uv run ruff check . && uv run ruff format --check .
```

## Proje yapısı

```
RapidQuizBackend/
├── apps/
│   ├── quiz/            # kategoriler, sorular, oyun oturumları; oyun kuralları services.py'de
│   ├── leaderboard/     # skor kayıtları, sıralama, isim doğrulama ve küfür filtresi
│   └── api_tests/       # uçtan uca API testleri
├── config/
│   ├── settings/        # base / dev / test / prod
│   ├── api.py           # ortak hata işleyici, /api/ altında JSON 404
│   ├── middleware.py    # sağlık kontrolü
│   └── urls.py          # /api/v1/ rotaları, /api/schema/, /api/docs/
├── data/questions/      # soru bankası (JSON, 5 × 60)
├── docs/                # proje ve yayın dokümanları (Türkçe)
├── .do/app.yaml         # DigitalOcean App Platform spec'i (şu an yayında değil)
├── Dockerfile           # çok aşamalı production imajı (gunicorn + WhiteNoise)
├── docker-compose.yml   # yerel PostgreSQL
└── pyproject.toml       # bağımlılıklar ve araç ayarları (uv)
```
