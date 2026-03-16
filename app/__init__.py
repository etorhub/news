"""Flask application factory."""

import os
from datetime import datetime
from pathlib import Path

import humanize
from dotenv import load_dotenv
from flask import Flask, Response, redirect, request, session, url_for

from app.cli import (
    fetch_feeds_cmd,
    make_admin,
    score_sources_cmd,
    seed_sources,
    validate_feeds_cmd,
)
from app.config import load_config
from app.db import users as db_users
from app.routes.admin import admin_bp
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

    @app.template_filter("naturaltime")
    def naturaltime_filter(dt: datetime | None) -> str:
        """Format datetime as relative time (e.g. '5 minutes ago', '2 days ago')."""
        if dt is None:
            return "—"
        return humanize.naturaltime(dt)

    app.register_blueprint(auth_bp)
    app.register_blueprint(setup_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(reader_bp)
    app.register_blueprint(admin_bp)

    @app.context_processor
    def inject_admin_flag():  # type: ignore[no-untyped-def]
        """Inject is_admin for nav link."""
        user_id = session.get("user_id")
        if not user_id:
            return {"is_admin": False}
        user = db_users.get_user_by_id(user_id)
        return {"is_admin": user.get("is_admin", False) if user else False}

    app.cli.add_command(seed_sources)
    app.cli.add_command(validate_feeds_cmd)
    app.cli.add_command(score_sources_cmd)
    app.cli.add_command(fetch_feeds_cmd)
    app.cli.add_command(make_admin)

    return app
