"""Tests for settings route."""

from unittest.mock import patch

import pytest
from flask.testing import FlaskClient


@pytest.fixture
def mock_sources() -> list[dict]:
    """Minimal sources list for settings form."""
    return [
        {"id": "s1", "name": "Source 1", "topics": ["general"]},
        {"id": "s2", "name": "Source 2", "topics": ["general"]},
    ]


@pytest.fixture
def mock_profile() -> dict:
    """Profile with all regeneration-affecting fields."""
    return {
        "user_id": 1,
        "location": "Barcelona",
        "language": "ca",
        "rewrite_tone": "Short sentences. Simple vocabulary. No jargon.",
        "filter_negative": False,
        "high_contrast": False,
        "source_ids": ["s1", "s2"],
        "topic_ids": ["general"],
    }


def test_settings_post_only_high_contrast_does_not_run_rewrite(
    client: FlaskClient,
    mock_sources: list[dict],
    mock_profile: dict,
) -> None:
    """When only high_contrast changes, run_rewrite_for_user is not called."""
    with (
        patch("app.routes.settings.load_sources", return_value=mock_sources),
        patch(
            "app.routes.settings.profile_service.get_profile_with_selections",
            return_value=mock_profile,
        ),
        patch(
            "app.routes.settings.profile_service.regeneration_needed",
            return_value=False,
        ),
        patch("app.routes.settings.profile_service.save_setup"),
        patch(
            "app.routes.settings.rewrite_service.run_rewrite_for_user",
        ) as mock_run_rewrite,
    ):
        with client.session_transaction() as sess:
            sess["user_id"] = 1

        response = client.post(
            "/settings/",
            data={
                "location": "Barcelona",
                "language": "ca",
                "rewrite_tone": "Short sentences. Simple vocabulary. No jargon.",
                "high_contrast": "on",
                "sources": ["s1", "s2"],
                "topics": ["general"],
            },
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert "saved=1" in response.location
        mock_run_rewrite.assert_not_called()


def test_settings_post_regeneration_field_runs_rewrite(
    client: FlaskClient,
    mock_sources: list[dict],
    mock_profile: dict,
) -> None:
    """When a regeneration-affecting field changes, run_rewrite_for_user is called."""
    with (
        patch("app.routes.settings.load_sources", return_value=mock_sources),
        patch(
            "app.routes.settings.profile_service.get_profile_with_selections",
            return_value=mock_profile,
        ),
        patch(
            "app.routes.settings.profile_service.regeneration_needed",
            return_value=True,
        ),
        patch("app.routes.settings.profile_service.save_setup"),
        patch(
            "app.routes.settings.rewrite_service.run_rewrite_for_user",
        ) as mock_run_rewrite,
    ):
        with client.session_transaction() as sess:
            sess["user_id"] = 1

        response = client.post(
            "/settings/",
            data={
                "location": "Barcelona",
                "language": "es",
                "rewrite_tone": "Short sentences. Simple vocabulary. No jargon.",
                "confirm_regenerate": "1",
                "sources": ["s1", "s2"],
                "topics": ["general"],
            },
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert "saved=1" in response.location
        mock_run_rewrite.assert_called_once_with(1)


def test_settings_post_regeneration_needed_shows_confirmation(
    client: FlaskClient,
    mock_sources: list[dict],
    mock_profile: dict,
) -> None:
    """When regeneration needed without confirm, shows confirmation block."""
    with (
        patch("app.routes.settings.load_sources", return_value=mock_sources),
        patch(
            "app.routes.settings.profile_service.get_profile_with_selections",
            return_value=mock_profile,
        ),
        patch(
            "app.routes.settings.profile_service.regeneration_needed",
            return_value=True,
        ),
        patch("app.routes.settings.profile_service.save_setup"),
        patch("app.routes.settings.rewrite_service.run_rewrite_for_user"),
        patch("app.db.users.get_user_by_id", return_value={"is_admin": False}),
    ):
        with client.session_transaction() as sess:
            sess["user_id"] = 1

        response = client.post(
            "/settings/",
            data={
                "location": "Barcelona",
                "language": "es",
                "rewrite_tone": "Short sentences. Simple vocabulary. No jargon.",
                "sources": ["s1", "s2"],
                "topics": ["general"],
            },
            follow_redirects=False,
        )

        assert response.status_code == 200
        assert b"Feed regeneration" in response.data
        assert b"Confirm and save" in response.data
