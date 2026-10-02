# Rapid Quiz — Backend

Rapid Quiz'in REST API'si (Django 6.1 + DRF). Ayrıntılar: [`docs/rapid-quiz-proje-dokumani.md`](docs/rapid-quiz-proje-dokumani.md).

## Hızlı başlangıç

```bash
docker compose up -d db
cp .env.example .env
uv sync
uv run manage.py migrate
uv run manage.py createsuperuser
uv run manage.py runserver
```

- Admin: http://localhost:8000/admin/
- API dokümantasyonu: http://localhost:8000/api/docs/
- Testler: `uv run pytest`
