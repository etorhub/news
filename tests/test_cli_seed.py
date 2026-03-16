"""Tests for CLI seed-sources command."""

import tempfile
from pathlib import Path

from app.config import load_sources


def test_load_sources_from_file() -> None:
    """load_sources returns list from valid YAML."""
    yaml_content = """
sources:
  - id: "test1"
    name: "Test Source"
    domain: "www.test.com"
    homepage_url: "https://www.test.com/"
    country_code: "ES"
    languages: ["ca"]
    feeds:
      - url: "https://www.test.com/feed"
        type: rss
        label: main
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        path = f.name
    try:
        sources = load_sources(path)
        assert len(sources) == 1
        assert sources[0]["id"] == "test1"
        assert sources[0]["name"] == "Test Source"
        assert len(sources[0]["feeds"]) == 1
        assert sources[0]["feeds"][0]["url"] == "https://www.test.com/feed"
    finally:
        Path(path).unlink(missing_ok=True)


def test_load_sources_missing_file() -> None:
    """load_sources returns empty list for missing file."""
    sources = load_sources("/nonexistent/path/sources.yaml")
    assert sources == []


def test_load_sources_empty_yaml() -> None:
    """load_sources returns empty list for YAML without sources key."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("other_key: []")
        path = f.name
    try:
        sources = load_sources(path)
        assert sources == []
    finally:
        Path(path).unlink(missing_ok=True)


def test_load_sources_default_path() -> None:
    """load_sources with None uses default config/sources.yaml."""
    sources = load_sources(None)
    # Default path may or may not exist; if it exists we should get sources
    assert isinstance(sources, list)
    if sources:
        assert "id" in sources[0]
        assert "name" in sources[0]
        assert "feeds" in sources[0]
