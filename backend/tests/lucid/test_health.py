"""T3: /health answers without the database. These tests have no `django_db` mark, so
pytest-django fails them on any database access."""

from asgiref.sync import async_to_sync
from django.test import AsyncClient, Client


def test_health_never_touches_the_database():
    response = Client().get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_over_asgi():
    response = async_to_sync(AsyncClient().get)("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-Id"]
