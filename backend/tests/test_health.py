"""Health endpoint tests."""

from sqlalchemy.exc import SQLAlchemyError


def test_api_health(client) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_database_health(client) -> None:
    response = client.get("/health/db")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_database_health_failure(client, monkeypatch) -> None:
    def fail_ping() -> None:
        raise SQLAlchemyError("simulated connection failure")

    monkeypatch.setattr("app.api.health.ping_database", fail_ping)

    response = client.get("/health/db")

    assert response.status_code == 503
    assert response.json()["detail"] == "Database is unreachable"
    assert "simulated" not in response.text
