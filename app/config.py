"""Load configuration from YAML files."""

from pathlib import Path
from typing import Any

import yaml

DEFAULTS: dict[str, Any] = {
    "llm": {
        "provider": "anthropic",
        "model": "claude-sonnet-4-20250514",
    },
    "embeddings": {
        "provider": "local",
        "model": "paraphrase-multilingual-MiniLM-L12-v2",
    },
    "extraction": {
        "enabled": True,
        "min_content_length": 200,
        "batch_size": 30,
        "rate_limit_per_domain": 2.0,
        "timeout": 30,
    },
    "schedule": {
        "fetch_interval_minutes": 60,
        "enrichment_cron": "10 * * * *",
        "cluster_cron": "5 * * * *",
        "rewrite_cron": "0 6 * * *",
        "rewrite_batch_size": 10,
        "fetcher": {
            "circuit_breaker_threshold": 5,
            "request_timeout_seconds": 30,
            "user_agent": "AccessibleNewsAggregator/0.1 (+https://github.com/accessible-news/aggregator)",
        },
    },
    "processing": {
        "articles_per_day": 10,
        "summary_sentences": 3,
        "cluster_window_hours": 24,
        "cluster_similarity_threshold": 0.82,
        "embed_batch_size": 50,
    },
    "server": {
        "port": 5000,
        "debug": False,
    },
}


def load_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """Load app config from YAML file, falling back to defaults if missing."""
    if config_path is None:
        config_path = Path(__file__).resolve().parent.parent / "config" / "app.yaml"
    path = Path(config_path)
    if not path.exists():
        return DEFAULTS.copy()
    with path.open() as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        return DEFAULTS.copy()
    return _deep_merge(DEFAULTS.copy(), data)


def load_sources(sources_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Load news sources from YAML file."""
    if sources_path is None:
        base = Path(__file__).resolve().parent.parent
        sources_path = base / "config" / "sources.yaml"
    path = Path(sources_path)
    if not path.exists():
        return []
    with path.open() as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict) or "sources" not in data:
        return []
    sources = data["sources"]
    return sources if isinstance(sources, list) else []


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Merge override into base recursively."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
