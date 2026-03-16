"""Health check and root route smoke tests."""

from flask.testing import FlaskClient


def test_root_redirects_to_login_when_unauthenticated(client: FlaskClient) -> None:
    """GET / redirects to login when not logged in."""
    response = client.get("/")
    assert response.status_code == 302
    assert "/login" in response.location


def test_favicon_returns_204(client: FlaskClient) -> None:
    """GET /favicon.ico returns 204."""
    response = client.get("/favicon.ico")
    assert response.status_code == 204


def test_health_returns_200(client: FlaskClient) -> None:
    """GET /health returns 200."""
    response = client.get("/health")
    assert response.status_code == 200


def test_health_returns_html(client: FlaskClient) -> None:
    """GET /health returns HTML content."""
    response = client.get("/health")
    assert "html" in response.content_type
    assert b"ok" in response.data
