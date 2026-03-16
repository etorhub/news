"""Flask application factory."""

import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Response, redirect, request, session, url_for

from app.cli import fetch_feeds_cmd, score_sources_cmd, seed_sources, validate_feeds_cmd
from app.config import load_config
from app.routes.auth import auth_bp
from app.routes.reader import reader_bp
from app.routes.settings import settings_bp
from app.routes.setup import setup_bp

load_dotenv()

PUBLIC_ENDPOINTS = {"auth.login", "auth.register", "health", "favicon"}


def create_app(config_path: str | Path | None = None) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__, template_folder="../templates")
    app.config["CONFIG"] = load_config(config_path)
    app.config["SECRET_KEY"] = os.environ.get(
        "SECRET_KEY", "dev-secret-key-change-in-production"
    )

    @app.before_request
    def require_auth():  # type: ignore[no-untyped-def]
        if request.endpoint in PUBLIC_ENDPOINTS:
            return None
        if request.endpoint is None:
            return None
        if not session.get("user_id"):
            return redirect(url_for("auth.login"))
        return None

    @app.route("/favicon.ico")
    def favicon() -> Response:
        """No favicon yet; return 204 to avoid 404s in logs."""
        return Response(status=204)

    @app.route("/health")
    def health() -> str:
        """Health check endpoint. Returns HTML per project rules."""
        return "<!DOCTYPE html><html><body><p>ok</p></body></html>"

    app.register_blueprint(auth_bp)
    app.register_blueprint(setup_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(reader_bp)

    app.cli.add_command(seed_sources)
    app.cli.add_command(validate_feeds_cmd)
    app.cli.add_command(score_sources_cmd)
    app.cli.add_command(fetch_feeds_cmd)

    return app
