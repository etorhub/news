"""Health check and root route smoke tests."""

from flask.testing import FlaskClient


def test_root_returns_200(client: FlaskClient) -> None:
    """GET / returns 200."""
    response = client.get("/")
    assert response.status_code == 200
    assert b"Accessible News Aggregator" in response.data


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
