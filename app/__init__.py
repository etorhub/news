"""Flask application factory."""

import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Response

from app.cli import fetch_feeds_cmd, score_sources_cmd, seed_sources, validate_feeds_cmd
from app.config import load_config

load_dotenv()


def create_app(config_path: str | Path | None = None) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config["CONFIG"] = load_config(config_path)
    app.config["SECRET_KEY"] = os.environ.get(
        "SECRET_KEY", "dev-secret-key-change-in-production"
    )

    @app.route("/")
    def index() -> str:
        """Root route. Placeholder until auth and feed are implemented."""
        return (
            "<!DOCTYPE html><html><body>"
            "<h1>Accessible News Aggregator</h1>"
            "<p>Coming soon. <a href='/health'>Health check</a></p>"
            "</body></html>"
        )

    @app.route("/favicon.ico")
    def favicon() -> Response:
        """No favicon yet; return 204 to avoid 404s in logs."""
        return Response(status=204)

    @app.route("/health")
    def health() -> str:
        """Health check endpoint. Returns HTML per project rules."""
        return "<!DOCTYPE html><html><body><p>ok</p></body></html>"

    app.cli.add_command(seed_sources)
    app.cli.add_command(validate_feeds_cmd)
    app.cli.add_command(score_sources_cmd)
    app.cli.add_command(fetch_feeds_cmd)

    return app
