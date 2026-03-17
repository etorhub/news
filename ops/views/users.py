"""Users view."""

from flask import Blueprint, Response, render_template

from app.db import admin as admin_db

users_bp = Blueprint("users", __name__)


@users_bp.route("/")
def index() -> Response:
    """Users list with usage stats."""
    users = admin_db.get_user_usage_stats()
    return render_template("ops/users.html", users=users)
