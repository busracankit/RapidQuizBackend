from unittest import mock

import pytest
from django.db.utils import OperationalError

pytestmark = pytest.mark.django_db


def test_health_ok_even_with_unknown_host(client):
    # DigitalOcean health check'i konteyner IP'siyle gelebilir; ALLOWED_HOSTS'a takılmamalı.
    response = client.get("/api/v1/health/", HTTP_HOST="10.244.3.17:8080")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_reports_db_failure(client):
    with mock.patch("config.middleware.connection.cursor", side_effect=OperationalError):
        response = client.get("/api/v1/health/")
    assert response.status_code == 503
    assert response.json()["database"] == "unavailable"


def test_other_paths_still_validate_host(client):
    response = client.get("/admin/login/", HTTP_HOST="evil.example.com")
    assert response.status_code == 400


def test_swagger_and_schema_available(client):
    assert client.get("/api/schema/").status_code == 200
    assert client.get("/api/docs/").status_code == 200
