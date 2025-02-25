import logging
import os
from datetime import datetime
from flask import Flask, jsonify, render_template, redirect, url_for, session, request, flash
from auth import auth_bp, login_required, google_bp
from db import close_db, get_db
from psycopg2.extras import RealDictCursor
from flask_dance.contrib.google import google
from logging.handlers import RotatingFileHandler
from sys import stdout

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev")

app.register_blueprint(auth_bp, url_prefix="/auth")
app.register_blueprint(google_bp, url_prefix="/login")

# if not app.debug:
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%d-%m-%Y %H:%M:%S",
    handlers=[
        logging.FileHandler("access.log"),
        logging.StreamHandler(stdout),
    ],
)
logger.info("Logging setup complete.")


@app.route("/")
@login_required
def index():
    user = session.get("name") or session.get("username").split("@")[0]
    return render_template("index.html", user=user)


@app.route("/google_login")
def google_login():
    resp = google.get("/oauth2/v2/userinfo")
    if resp.ok:
        user_info = resp.json()

        db = get_db()
        with db.cursor() as cursor:
            cursor.execute(
                "INSERT INTO users (username, password_hash, role_name) VALUES (%s, %s, %s) "
                "ON CONFLICT (username) DO NOTHING RETURNING user_id",
                (user_info.get("email"), "google_authorised", "Worker"),
            )
            user_row = cursor.fetchone()
            if user_row is not None:
                user_id = user_row[0]
            else:
                # if nothing was returned, the user already exists; select the user_id.
                cursor.execute("SELECT user_id FROM users WHERE username = %s", (user_info.get("email"),))
                user_id = cursor.fetchone()[0]
            db.commit()
            session.clear()
            session["user_id"] = user_id
            session["username"] = user_info.get("email")
            session["name"] = user_info.get("name")

            session["profile_pic"] = user_info.get("picture")
            session["role_name"] = "Worker"

    return redirect(url_for("index"))


@app.route("/projects", methods=["GET"])
def projects():
    if "role_name" not in session or session["role_name"] not in ["Admin", "Manager"]:
        logger.info("Unnauthorized access to projects page")
        return "Unauthorized Access"
    db = get_db()
    with db.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute("SELECT * FROM projects")
        projects = cursor.fetchall()

    return render_template("project_charter.html", projects=projects)


@app.route("/privacy", methods=["GET"])
def privacy():
    return render_template("privacy_policy.html")


@app.before_request
def log_ip():
    ip_address = request.remote_addr
    logger.info(f"Incoming request from IP: {ip_address}, URL: {request.url}")


@app.route("/create_project", methods=["POST"])
def create_project():
    # Only Admin/Manager should be able to create projects
    if "role_name" not in session or session["role_name"] not in ["Admin", "Manager"]:
        logger.info("Unnauthorized access to projects page")
        return "Unauthorized Access"
    # if session["role_name"] == "Admin":
    #     return "Only managers can create tasks"
    # print(session["role_name"])
    if request.method == "POST":
        project_name = request.form["project_name"]
        description = request.form["description"]
        start_date = datetime.strptime(request.form["start_date"], "%Y-%m-%d")
        end_date = datetime.strptime(request.form["end_date"], "%Y-%m-%d")
        manager_id = session["user_id"]  # if the logged in user is manager
        db = get_db()
        with db.cursor() as cursor:
            cursor.execute(
                "INSERT INTO projects (project_name, description, start_date, end_date, manager_id) VALUES (%s, %s, %s, %s, %s)",
                (project_name, description, start_date, end_date, manager_id),
            )
            db.commit()
        logger.info("Project created successfully")
        flash("Project created successfully!", "success")
        return redirect(url_for("projects"))


@app.route("/tasks", methods=["GET"])
@login_required
def tasks():
    db = get_db()
    with db.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute("SELECT * FROM tasks where assigned_to = %s", (session["user_id"],))
        tasks = cursor.fetchall()
        cursor.execute("SELECT * FROM projects")
        projects = cursor.fetchall()
        cursor.execute("SELECT * FROM users where role_name = 'Worker'")
        workers = cursor.fetchall()
    return render_template(
        "tasks.html",
        tasks=tasks,
        projects=projects,
        workers=workers,
    )


@app.route("/create_task", methods=["POST"])
@login_required
def create_task():

    if "role_name" not in session or session["role_name"] not in ["Admin", "Manager"]:
        return "Unauthorized Access"
    # if session["role_name"] == "Admin":
    #     return "Only managers can create tasks"

    if request.method == "POST":
        task_name = request.form["task_name"]
        task_description = request.form["task_description"]

        deadline = request.form["deadline"]
        assigned_to = request.form["assigned_to"]
        project_id = request.form["project_id"]
        db = get_db()
        with db.cursor() as cursor:
            cursor.execute(
                "INSERT INTO tasks (task_name, task_description, deadline, project_id, assigned_to) VALUES (%s, %s, %s, %s, %s)",
                (task_name, task_description, deadline, project_id, assigned_to),
            )
            db.commit()
        logger.info("Task created successfully")
        flash("Task created successfully!", "success")
        return redirect(url_for("tasks"))


@app.route("/api/projects", methods=["GET"])
@login_required
def get_projects():
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute(
            """
            SELECT json_agg(
                json_build_object(
                    'project_id', project_id,
                    'project_name', project_name,
                    'description', description,
                    'start', start_date,
                    'end', end_date,
                    'manager', users.username,
                    'tasks', (
                        SELECT json_agg(
                            json_build_object(
                                'task_id', task_id,
                                'task_name', task_name,
                                'description', task_description,
                                'end', deadline,
                                'status', status
                            )
                        ) FROM tasks WHERE project_id = projects.project_id
                    )
    
                )
            ) FROM projects JOIN users ON projects.manager_id = users.user_id
        """
        )
        projects = cursor.fetchone()[0]

    return jsonify(projects if projects else [])


@app.route("/api/tasks", methods=["GET"])
@login_required
def get_tasks():
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute(
            """
            SELECT json_agg(
                json_build_object(
                    'task_id', task_id,
                    'task_name', task_name,
                    'description', task_description,
                    'start', deadline,
                    'project_id', project_id,
                    'status', status
                )
            ) FROM tasks WHERE assigned_to = %s
        """,
            (session["user_id"],),
        )
        result = cursor.fetchone()[0]
    return jsonify(result if result else [])


@app.route("/events", methods=["GET"])
@login_required
def events():
    db = get_db()
    with db.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
                SELECT 
                    e.event_id,
                    e.event_name, 
                    e.event_description, 
                    e.event_date, 
                    r.username AS requested_by_username, 
                    a.username AS approved_by_username
                FROM events e
                JOIN users r ON e.requested_by = r.user_id
                LEFT JOIN users a ON e.approved_by = a.user_id;
            """
        )
        events = cursor.fetchall()
    return render_template("events.html", events=events)


@app.route("/request_event", methods=["POST"])
@login_required
def request_event():
    if request.method == "POST":
        event_name = request.form["event_name"]
        event_description = request.form["event_description"]
        event_date = request.form["event_date"]
        requested_by = session["user_id"]
        db = get_db()
        with db.cursor() as cursor:
            cursor.execute(
                "INSERT INTO events (event_name, event_description, event_date, requested_by) VALUES (%s, %s, %s, %s)",
                (event_name, event_description, event_date, requested_by),
            )
            db.commit()
        logger.info("Event requested successfully")
        flash("Event requested successfully!", "success")
        return redirect(url_for("events"))


@app.route("/approve_event/<int:event_id>", methods=["POST"])
@login_required
def approve_event(event_id):
    db = get_db()
    approver = session["user_id"]
    with db.cursor() as cursor:
        cursor.execute(
            "UPDATE events SET approved_by = %s WHERE event_id = %s",
            (approver, event_id),
        )
        db.commit()
    logger.info("Event approved successfully")
    flash("Event approved successfully!", "success")
    return redirect(url_for("events"))


@app.route("/api/events", methods=["GET"])
@login_required
def get_events():
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute(
            """
            SELECT json_agg(
                json_build_object(
                    'event_id', e.event_id,
                    'title', e.event_name,
                    'start', e.event_date,
                    'description', e.event_description,
                    'requested_by_username', r.username,
                    'approved_by_username', a.username
                )
            ) FROM events e
            JOIN users r ON e.requested_by = r.user_id
            LEFT JOIN users a ON e.approved_by = a.user_id;
            """
        )
        result = cursor.fetchone()[0]

    return jsonify(result if result else [])


@app.route("/about", methods=["GET"])
@login_required
def about():
    return render_template("about.html", events=events)


@app.context_processor
def inject_globals():
    return {"current_year": datetime.now().year}


@app.teardown_appcontext
def shutdown_appcontext(exception=None):
    close_db()


if __name__ == "__main__":
    app.run(debug=True, port=5000)
