# Rapid Quiz — DigitalOcean'a yayın

> **Not (4 Ekim 2026):** vf kurulumu doctl yerine **DO panelinden (tarayıcı) manuel** yapacak. Aşağıdaki
> doctl adımları alternatif/referanstır; panelde aynı bileşen ve değerler kullanılır (bkz. `CLAUDE.md` › Deploy).

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
