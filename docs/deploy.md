# Rapid Quiz — DigitalOcean'a yayın

> **Durum (7 Ekim 2026):** Uygulama şu an **yayında değil.** Aşağıdaki kurulum Ekim 2026'da denendi ve çalıştı,
> ardından kaynaklar maliyet nedeniyle silindi. Bu dosya yeniden kurulum rehberidir.

> **Not:** Kurulum 5 Ekim 2026'da doctl yerine **DO panelinden** yapıldı; güncel akış hemen aşağıdaki
> "Panelden kurulum" bölümünde. Sonraki doctl adımları alternatif/referanstır.

## Panelden kurulum — 5 Ekim 2026'da uygulanan akış

Gerçek kurulum DO panelinden (doctl'siz) yapıldı ve çalıştı (şu an kapalı). Uygulama adı DO'nun verdiği ad,
adres `https://<app-adı>.ondigitalocean.app`, bölge FRA1, veritabanı kümesi `db-pgsql-rapidquiz`. Bileşenler: `api` (Dockerfile), frontend statik sitesi, `migrate` ve `cleanup-sessions` job'ları.

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

---

Backend (Django) ve frontend (Vue) **tek bir App Platform uygulamasında** çalışır:

| Yol | Bileşen |
| --- | --- |
| `/api/…`, `/admin/…`, `/static/…` | `api` — Dockerfile'dan, gunicorn, port 8080 |
| diğer her şey (`/`, `/oyun`, …) | `web` — Vue build'i (`dist/`), statik site |

Aynı adreste oldukları için CORS gerekmez; frontend API'ye `/api/v1` ile gider. Veritabanı ayrı bir
**Managed PostgreSQL 18** kümesidir. Spec: `.do/app.yaml`. Alan adı şimdilik DigitalOcean'ın verdiği
`https://rapid-quiz-xxxxx.ondigitalocean.app` adresidir (alan adı eklemek için › 9).

> Yaklaşık aylık maliyet (güncel fiyatları DO panelinden kontrol edin): `api` servisi (1 vCPU / 1 GB) ~12 $,
> Managed PostgreSQL (en küçük, 1 düğüm) ~15 $, statik site ücretsiz katmanda; job'lar çalıştıkları süre kadar.

## 0. Önkoşullar

- DigitalOcean hesabı (ödeme yöntemi ekli).
- GitHub'da iki repo: `busracankit/RapidQuizBackend`, `busracankit/RapidQuizFrontend`.
- Mac'te Homebrew.

## 1. Kodları GitHub'a gönder

İki repoda da (PyCharm › Git › Push ya da Terminal):

```bash
cd ~/PycharmProjects/RapidQuizBackend  && git push -u origin main
cd ~/PycharmProjects/RapidQuizFrontend && git push -u origin main
```

GitHub › **Actions** sekmesinde CI'nin yeşil olduğunu kontrol et. (`main` korumalı yapılacaksa:
Settings › Branches › kural ekle › "Require status checks to pass".)

## 2. DigitalOcean'a GitHub erişimi ver

DO panelinde **Apps › Create App › GitHub** seç, "Install & Authorize" ile DigitalOcean GitHub
uygulamasına **iki repoya** erişim ver. Uygulamayı panelden oluşturma; sihirbazdan çık (› 5'te spec ile
oluşturacağız).

## 3. doctl kur ve giriş yap

```bash
brew install doctl
doctl auth init        # panel › API › Generate New Token (Full Access) — token'ı yalnızca buraya yapıştır
doctl account get      # e-posta görünüyorsa tamam
```

## 4. Veritabanı kümesini oluştur (Managed PostgreSQL 18, Frankfurt)

```bash
doctl databases create rapid-quiz-db --engine pg --version 18 \
  --region fra1 --size db-s-1vcpu-1gb --num-nodes 1
doctl databases list   # Status "online" olana kadar bekle (5–10 dk)
```

## 5. Uygulamayı oluştur

`DJANGO_SECRET_KEY` repoya yazılmaz: spec'in geçici bir kopyasında rastgele bir değerle değiştirilir,
DigitalOcean bu değeri şifreleyerek saklar.

```bash
cd ~/PycharmProjects/RapidQuizBackend
SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(50))")
sed "s|__DJANGO_SECRET_KEY__|$SECRET|" .do/app.yaml > /tmp/rapid-quiz-app.yaml
doctl apps create --spec /tmp/rapid-quiz-app.yaml
rm /tmp/rapid-quiz-app.yaml
doctl apps list        # ID ve "Default Ingress" (adres) sütunlarını not et
```

İlk deploy 5–10 dk sürer: Docker imajı ve Vue build'i hazırlanır, `migrate` job'ı migration'ları ve
`load_questions`'ı çalıştırır, ardından `api` ve `web` yayına girer. İzlemek için panel › Apps ›
rapid-quiz › Activity ya da `doctl apps logs <app-id> --type build`.

## 6. Veritabanına yalnızca uygulamanın erişmesine izin ver

```bash
DB_ID=$(doctl databases list --format ID,Name --no-header | awk '/rapid-quiz-db/{print $1}')
APP_ID=$(doctl apps list --format ID,Spec.Name --no-header | awk '/rapid-quiz/{print $1}')
doctl databases firewalls append $DB_ID --rule app:$APP_ID
```

## 7. Admin kullanıcısı

```bash
doctl apps console $APP_ID api
# açılan konsolda:
python manage.py createsuperuser
```

## 8. Kontrol

- `https://<adres>/api/v1/health/` → `{"status": "ok"}`
- `https://<adres>/` → ana sayfa, 5 kategori
- `https://<adres>/admin/` → giriş, Sorular ekranında 300 soru
- Bir oyun oyna, skoru kaydet.

## Sonraki deploylar

- `main`'e push → ilgili bileşen otomatik yeniden deploy edilir (backend push'unda önce `migrate` job'ı).
- Soru eklemek: `data/questions/*.json` düzenle → push (deploy sırasında `load_questions` çalışır) ya da admin'den.
- Spec değişikliği: `doctl apps update $APP_ID --spec <secret eklenmiş geçici kopya>` — ya da secret'ı
  korumak için panel › Settings › App Spec üzerinden düzenle.
- Sorunlu deploy: panel › Activity › önceki deploy › **Rollback**.
- Yarım kalan oturum temizliği her gün 04:00'te (İstanbul) `cleanup-sessions` job'ı ile çalışır.

## 9. Alan adı eklemek (ileride)

Panel › Apps › rapid-quiz › Settings › Domains › Add Domain (ör. `rapidquiz.app`); DNS'i DO'ya yönlendir ya da
CNAME ekle. Sertifika otomatik alınır. `DJANGO_ALLOWED_HOSTS` ve `CSRF_TRUSTED_ORIGINS` `${APP_DOMAIN}`
kullandığından birincil alan adı değişince kendiliğinden güncellenir.
