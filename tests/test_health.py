"""Health check smoke test."""

from flask.testing import FlaskClient


def test_health_returns_200(client: FlaskClient) -> None:
    """GET /health returns 200."""
    response = client.get("/health")
    assert response.status_code == 200


def test_health_returns_html(client: FlaskClient) -> None:
    """GET /health returns HTML content."""
    response = client.get("/health")
    assert "html" in response.content_type
    assert b"ok" in response.data
