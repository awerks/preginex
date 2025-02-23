import functools
import os
import logging
from db import get_db
from flask_dance.contrib.google import make_google_blueprint
from flask import Blueprint, flash, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash

logger = logging.getLogger(__name__)
# for local testing
# if os.environ.get("FLASK_ENV", "development") == "development":
logger.info("Setting up environment variables for local testing.")
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "true"
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "true"

auth_bp = Blueprint("auth", __name__, template_folder="templates/auth")
google_client_id = os.environ.get(
    "GOOGLE_CLIENT_ID",
)
google_client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")


google_bp = make_google_blueprint(
    client_id=google_client_id,
    client_secret=google_client_secret,
    scope=["profile", "email"],
    redirect_to="google_login",
)


def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if "username" not in session:
            return redirect(url_for("auth.login"))

        return view(**kwargs)

    return wrapped_view


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        db = get_db()
        with db.cursor() as cursor:
            cursor.execute("SELECT user_id, password_hash, role_name FROM users WHERE username = %s", (username,))
            user = cursor.fetchone()
            if user and check_password_hash(user[1], password):
                session.clear()
                session["user_id"] = user[0]
                session["username"] = username
                session["role_name"] = user[2]
            else:
                return render_template("login.html", error="Invalid credentials")

        return redirect(url_for("index"))
    return render_template("login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        role_name = request.form.get("role_name")
        db = get_db()

        with db.cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
            existing_user = cursor.fetchone()
            if existing_user:
                return render_template("register.html", error="Username already exists")

            cursor.execute(
                "INSERT INTO users (username, password_hash, role_name) VALUES (%s, %s, %s) RETURNING user_id",
                (username, generate_password_hash(password), role_name),
            )
            user_id = cursor.fetchone()[0]
            db.commit()

            session.clear()
            session["username"] = username
            session["user_id"] = user_id
            session["role_name"] = role_name

        return redirect(url_for("index"))
    return render_template("register.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))
