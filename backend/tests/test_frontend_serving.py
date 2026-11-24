"""Serving the built React app from FastAPI (production/Docker mode).

These tests build a tiny fake "dist" folder; they do not need Node or a real
frontend build. They also prove that the default app (no FRONTEND_DIST_DIR) is
unchanged, which is what local development uses.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import create_app

INDEX_HTML = "<!doctype html><title>CLM test shell</title><div id='root'></div>"


@pytest.fixture
def dist_dir(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (dist / "assets" / "app-abc123.js").write_text("console.log('ok')", encoding="utf-8")
    (dist / "favicon.svg").write_text("<svg></svg>", encoding="utf-8")
    (dist / "robots.txt").write_text("User-agent: *\n", encoding="utf-8")
    # A file next to dist must never be reachable through path tricks.
    (tmp_path / "secret.txt").write_text("TOP-SECRET", encoding="utf-8")
    return dist


@pytest.fixture
def spa_client(dist_dir, db_session):
    application = create_app(frontend_dist=dist_dir)
    application.dependency_overrides[get_db] = lambda: db_session
    with TestClient(application) as test_client:
        yield test_client


def test_root_and_react_routes_return_index(spa_client):
    for path in ("/", "/login", "/contracts", "/contracts/123", "/contracts/123/edit"):
        response = spa_client.get(path)
        assert response.status_code == 200, path
        assert "CLM test shell" in response.text, path
        assert response.headers["content-type"].startswith("text/html")
        assert response.headers["cache-control"] == "no-cache"


def test_head_request_for_react_route_works(spa_client):
    assert spa_client.head("/contracts/123").status_code == 200


def test_hashed_assets_and_public_files_are_served(spa_client):
    asset = spa_client.get("/assets/app-abc123.js")
    assert asset.status_code == 200
    assert "console.log" in asset.text

    assert spa_client.get("/favicon.svg").status_code == 200
    assert spa_client.get("/robots.txt").text.startswith("User-agent")


def test_missing_files_are_404_not_index(spa_client):
    for path in ("/assets/missing.js", "/logo.png", "/contracts/report.pdf"):
        response = spa_client.get(path)
        assert response.status_code == 404, path
        assert "CLM test shell" not in response.text, path


def test_path_traversal_cannot_leave_the_dist_folder(spa_client):
    for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/assets/../../secret.txt"):
        response = spa_client.get(path)
        assert "TOP-SECRET" not in response.text, path


def test_unknown_api_paths_stay_json_404(spa_client):
    for path in ("/api/does-not-exist", "/api/contracts/x/y/z", "/health/unknown", "/docs/nope"):
        response = spa_client.get(path)
        assert response.status_code == 404, path
        assert response.headers["content-type"].startswith("application/json"), path
        assert response.json() == {"detail": "Not Found"}, path
        assert "CLM test shell" not in response.text, path


def test_existing_endpoints_are_unaffected(spa_client):
    assert spa_client.get("/health").json() == {"status": "ok"}
    assert spa_client.get("/health/db").json()["database"] == "ok"

    docs = spa_client.get("/docs")
    assert docs.status_code == 200
    assert "swagger" in docs.text.lower()
    assert "CLM test shell" not in docs.text

    schema = spa_client.get("/openapi.json")
    assert schema.status_code == 200
    assert "/api/contracts" in schema.json()["paths"]
    # The catch-all must not show up in the API documentation.
    assert "/{full_path}" not in schema.json()["paths"]

    # Real API routes still answer (unauthenticated -> 401 JSON, not HTML).
    unauthenticated = spa_client.get("/api/contracts")
    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["detail"] == "Not authenticated"

    csrf = spa_client.get("/api/auth/csrf")
    assert csrf.status_code == 200
    assert "csrf_token" in csrf.json()


def test_state_changing_api_calls_still_require_csrf(spa_client):
    response = spa_client.post(
        "/api/auth/login", json={"email": "x@example.com", "password": "whatever-123"}
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "CSRF validation failed"


def test_default_app_does_not_serve_a_frontend(client):
    """Local development: FRONTEND_DIST_DIR is unset, so nothing changes."""
    response = client.get("/contracts/123")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_incomplete_dist_folder_fails_at_startup(tmp_path):
    with pytest.raises(RuntimeError, match="built frontend"):
        create_app(frontend_dist=tmp_path)
