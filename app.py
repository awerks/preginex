import logging
import os
import sentry_sdk
from datetime import datetime
from flask import Flask, flash, jsonify, render_template, redirect, url_for, session, request
from auth import auth_bp, login_required, admin_or_manager_required, google_bp
from db import close_db, get_db
from psycopg2.extras import RealDictCursor
from flask_dance.contrib.google import google
from sys import stdout
from werkzeug.middleware.proxy_fix import ProxyFix
from sentry_sdk.integrations.flask import FlaskIntegration
from utils import send_email, cache_static
from flask_caching import Cache

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev")
app.jinja_env.globals["now"] = datetime.now
app.jinja_env.trim_blocks = True
app.jinja_env.lstrip_blocks = True


if not app.debug:
    sentry_sdk.init(dsn=os.environ.get("SENTRY_SDK"), integrations=[FlaskIntegration()])

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
config = {
    "CACHE_TYPE": "RedisCache",
    "CACHE_REDIS_URL": os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    "CACHE_KEY_PREFIX": "awerks_",
    "CACHE_DEFAULT_TIMEOUT": 60,
}
app.config.from_mapping(config)
cache = Cache(app)


def user_cache(timeout=60, base_key="view"):
    def decorator(view_func):
        key_prefix = lambda: f"{base_key}/{session.get('user_id', 'anon')}"  # noqa: E731
        return cache.cached(timeout=timeout, key_prefix=key_prefix)(view_func)

    return decorator


def cache_delete_projects_tasks():
    user_id = session.get("user_id")
    for key in [
        "projects-html",
        "projects-json",
        "tasks-html",
        "tasks-json",
        "analysis-html",
    ]:
        cache.delete(f"{key}/{user_id}")


def cache_delete_events():
    user_id = session.get("user_id")
    for key in ["events-html", "events-json"]:
        cache.delete(f"{key}/{user_id}")


@app.route("/")
@cache_static
def index():
    user = session.get("name")
    if not user and session.get("username"):
        user = session["username"].split("@")[0]
    return render_template("index.html", user=user)


@app.route("/google_login")
def google_login():
    resp = google.get(
        "https://people.googleapis.com/v1/people/me", params={"personFields": "birthdays,names,emailAddresses,photos"}
    )
    if resp.ok:
        user_info = resp.json()

        emails = user_info.get("emailAddresses", [])
        email = emails[0].get("value").lower() if emails else "None"
        username = email.split("@")[0]
        names = user_info.get("names", [])
        role_name = "Admin"
        if names:
            first_name = names[0].get("givenName")
            last_name = names[0].get("familyName")
            display_name = names[0].get("displayName")
        else:
            first_name = "None"
            last_name = None
            display_name = None

        birthdays = user_info.get("birthdays", [])
        if birthdays and "date" in birthdays[0]:
            bday = birthdays[0]["date"]
            year = bday.get("year", 1970)
            month = bday.get("month", 1)
            day = bday.get("day", 1)
            birthday_str = f"{year}-{month:02d}-{day:02d}"
        else:
            birthday_str = None
        photos = user_info.get("photos", [])
        if photos:
            profile_pic = photos[0].get("url")
        else:
            profile_pic = None

        db = get_db()
        with db.cursor() as cursor:
            cursor.execute("SELECT user_id, role_name, second_name FROM users WHERE email = %s", (email,))
            user_row = cursor.fetchone()
            if user_row:
                user_id, role_name, second_name = user_row
                if second_name and not last_name:
                    display_name = f"{first_name} {second_name}"
            else:
                cursor.execute(
                    """
                    INSERT INTO users (username, email, password_hash, role_name, first_name, second_name, birthday_date, confirmed)
                    VALUES (%s, %s, %s, %s, %s, %s,%s, %s)
                    ON CONFLICT (username) DO NOTHING RETURNING user_id
                    """,
                    (username, email, "google_authorised", "Worker", first_name, last_name, birthday_str, True),
                )
                db.commit()
                user_id = cursor.fetchone()[0]

            session.clear()
            session.update(
                {
                    "user_id": user_id,
                    "username": email,
                    "name": display_name or email,
                    "profile_pic": profile_pic,
                    "role_name": role_name,
                    "confirmed": True,
                }
            )

    return redirect(url_for("index"))


@app.route("/projects", methods=["GET"])
@login_required
@admin_or_manager_required
@user_cache(base_key="projects-html")
def projects():
    db = get_db()
    with db.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute("SELECT * FROM projects")
        projects = cursor.fetchall()

    return render_template("project_charter.html", projects=projects)


@app.route("/privacy", methods=["GET"])
@cache_static
def privacy():
    return render_template("privacy_policy.html")


@app.before_request
def log_ip():
    ip_address = request.remote_addr
    logger.info(f"Incoming request from IP: {ip_address}, URL: {request.url}")


@app.route("/create_project", methods=["POST"])
@login_required
@admin_or_manager_required
def create_project():

    project_name = request.form.get("project_name")
    description = request.form.get("description")
    start_date_str = request.form.get("start_date")
    end_date_str = request.form.get("end_date")

    if not all([project_name, description, start_date_str, end_date_str]):
        logger.info("Missing required fields for project creation")
        flash("Missing required fields.", "error")

    try:
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
    except ValueError:
        logger.info("Invalid date format for project creation")
        return jsonify(error="Invalid date format. Please use YYYY-MM-DD."), 400

    if start_date > end_date:
        logger.info("Start date cannot be after end date for project creation")
        return jsonify(error="Start date cannot be after end date."), 400

    manager_id = session["user_id"]
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute(
            "INSERT INTO projects (project_name, description, start_date, end_date, manager_id) VALUES (%s, %s, %s, %s, %s)",
            (project_name, description, start_date, end_date, manager_id),
        )
        db.commit()
    logger.info("Project created successfully")
    cache_delete_projects_tasks()
    return redirect(url_for("projects"))


@app.route("/delete_project", methods=["POST"])
@login_required
@admin_or_manager_required
def delete_project():

    db = get_db()
    project_id = request.get_json().get("project_id")
    if not project_id:
        logger.info("Project ID not provided for deletion")
        return jsonify(error="Project ID not provided."), 400

    with db.cursor() as cursor:
        cursor.execute("DELETE FROM projects WHERE project_id = %s", (project_id,))
        db.commit()
    logger.info(f"Project with ID {project_id} deleted successfully")
    cache_delete_projects_tasks()
    return jsonify(success=True), 200


@app.route("/edit_project", methods=["POST"])
@login_required
@admin_or_manager_required
def edit_project():

    json_data = request.get_json() or {}
    if not json_data:
        logger.info("No JSON data provided for project edit")
        return jsonify(error="No JSON data provided."), 400

    project_id = json_data.get("project_id")
    project_name = json_data.get("project_name").strip()
    description = json_data.get("description").strip()
    if not all([project_name, description]):
        logger.info("Missing required fields for project edit")
        return jsonify(error="Missing required fields."), 400

    db = get_db()
    with db.cursor() as cursor:
        cursor.execute(
            """
            UPDATE projects 
            SET project_name = %s, description = %s
            WHERE project_id = %s
            """,
            (project_name, description, project_id),
        )
        db.commit()
    logger.info(f"Project with ID {project_id} edited successfully")
    cache_delete_projects_tasks()
    return jsonify(success=True), 200


@app.route("/tasks", methods=["GET"])
@user_cache(base_key="tasks-html")
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
@admin_or_manager_required
def create_task():

    if request.method == "POST":
        task_name = request.form.get("task_name")
        task_description = request.form.get("task_description")
        deadline_str = request.form.get("deadline")
        assigned_to_str = request.form.get("assigned_to")
        project_id_str = request.form.get("project_id")

        if not all([task_name, task_description, deadline_str, assigned_to_str, project_id_str]):
            logger.info("Missing required fields for task creation")
            flash("Missing required fields.", "error")

        try:
            deadline = datetime.strptime(deadline_str, "%Y-%m-%d").date()
            assigned_to = int(assigned_to_str)
            project_id = int(project_id_str)
        except ValueError:
            logger.info("Invalid format for deadline, assigned_to, or project_id.")
            flash("Invalid format for deadline, assigned_to, or project_id.", "error")

        if deadline < datetime.now().date():
            logger.info("Deadline cannot be in the past for task creation.")
            flash("Deadline cannot be in the past.", "error")
        db = get_db()
        with db.cursor() as cursor:
            cursor.execute("SELECT project_id FROM projects WHERE project_id = %s", (project_id,))
            if cursor.fetchone() is None:
                logger.info(f"Attempted to create task for non-existent project_id: {project_id}")
                flash("Project does not exist.", "error")

            cursor.execute("SELECT user_id FROM users WHERE user_id = %s", (assigned_to,))
            if cursor.fetchone() is None:
                logger.info(f"Attempted to assign task to non-existent user_id: {assigned_to}")
                flash("User does not exist.", "error")

        db = get_db()
        with db.cursor() as cursor:
            cursor.execute(
                "INSERT INTO tasks (task_name, task_description, deadline, project_id, assigned_to) VALUES (%s, %s, %s, %s, %s)",
                (task_name, task_description, deadline, project_id, assigned_to),
            )
            db.commit()
        logger.info("Task created successfully")
        cache_delete_projects_tasks()
        with db.cursor() as cursor:
            cursor.execute("SELECT email FROM users WHERE user_id = %s", (assigned_to,))
            assigned_to_email = cursor.fetchone()
            if assigned_to_email:
                assigned_to_email = assigned_to_email[0].strip()
                logger.info(f"Sending email to {assigned_to_email}")
                send_email(
                    subject="New Task Assigned",
                    to_address=assigned_to_email,
                    html_body=render_template(
                        "email/task_assigned.html",
                        task_name=task_name,
                        task_description=task_description,
                        deadline=deadline,
                    ),
                )
            else:
                logger.info(f"Assigned user with ID {assigned_to} does not exist.")

        return redirect(url_for("tasks"))


@app.route("/api/tasks/<int:task_id>", methods=["DELETE"])
@login_required
@admin_or_manager_required
def delete_task(task_id):
    db = get_db()
    if not task_id:
        logger.info("Task ID not provided for deletion")
        return jsonify(error="Task ID not provided."), 400

    with db.cursor() as cursor:
        cursor.execute("DELETE FROM tasks WHERE task_id = %s", (task_id,))
        db.commit()
    logger.info(f"Task with ID {task_id} deleted successfully")
    cache_delete_projects_tasks()
    return jsonify(success=True), 200


@app.route("/api/projects", methods=["GET"])
@user_cache(base_key="projects-json")
@login_required
@admin_or_manager_required
def get_projects():
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute(
            """
            SELECT json_agg(
                json_build_object(
                    'project_id', p.project_id,
                    'project_name', p.project_name,
                    'description', p.description,
                    'start', p.start_date,
                    'end', p.end_date,
                    'manager', u_manager.username,
                    'tasks', (
                        SELECT json_agg(
                            json_build_object(
                                'task_id', t.task_id,
                                'task_name', t.task_name,
                                'description', t.task_description,
                                'end', t.deadline,
                                'status', t.status,
                                'assigned_username', u_task.username -- Added assigned_username
                            )
                        ) FROM tasks t
                        LEFT JOIN users u_task ON t.assigned_to = u_task.user_id 
                        WHERE t.project_id = p.project_id
                    )
                )
            ) FROM projects p
            JOIN users u_manager ON p.manager_id = u_manager.user_id
        """
        )
        projects = cursor.fetchone()[0]

    return jsonify(projects if projects else [])


@app.route("/api/tasks", methods=["GET"])
@user_cache(base_key="tasks-json")
@login_required
def get_tasks():
    db = get_db()
    if session["role_name"] in ["Admin", "Manager"]:
        with db.cursor() as cursor:
            cursor.execute(
                """
                SELECT json_agg(
                    json_build_object(
                        'task_id', task_id,
                        'title', task_name,
                        'description', task_description,
                        'start', deadline,
                        'project_id', project_id,
                        'assigned_username', u.username,
                        'status', status
                    )
                ) FROM tasks t
                LEFT JOIN users u ON t.assigned_to = u.user_id
            """,
                (session.get("user_id"),),
            )
            result = cursor.fetchone()[0]

    else:
        with db.cursor() as cursor:
            cursor.execute(
                """
                SELECT json_agg(
                    json_build_object(
                        'task_id', task_id,
                        'title', task_name,
                        'description', task_description,
                        'start', deadline,
                        'project_id', project_id,
                        'assigned_username', %s,
                        'status', status
                    )
                ) FROM tasks t
                WHERE t.assigned_to = %s
            """,
                (
                    session.get("username"),
                    session.get("user_id"),
                ),
            )
            result = cursor.fetchone()[0]

    return jsonify(result if result else [])


@app.route("/events", methods=["GET"])
@user_cache(base_key="events-html")
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
        print()
    return render_template("events.html", events=events)


@app.route("/request_event", methods=["POST"])
@login_required
def request_event():
    event_name = request.form.get("event_name")
    event_description = request.form.get("event_description")
    event_date_str = request.form.get("event_date")
    requested_by = session.get("user_id")

    if not all([event_name, event_description, event_date_str, requested_by]):
        logger.info("Missing required fields for event request")
        flash("Missing required fields.", "error")

    try:
        event_date = datetime.strptime(event_date_str, "%Y-%m-%d").date()
    except ValueError:
        logger.info("Invalid date format for event request")
        flash("Invalid date format. Please use YYYY-MM-DD.", "error")

    if event_date < datetime.now().date():
        logger.info("Event date cannot be in the past for event request.")
        flash("Event date cannot be in the past.", "error")

    if len(event_name) > 255:
        logger.info("Event name too long for event request.")
        flash("Event name is too long (maximum 255 characters).", "error")

    if len(event_description) > 512:
        logger.info("Event description too long for event request.")
        flash("Event description is too long (maximum 512 characters).", "error")

    db = get_db()
    with db.cursor() as cursor:
        cursor.execute(
            "INSERT INTO events (event_name, event_description, event_date, requested_by) VALUES (%s, %s, %s, %s)",
            (event_name, event_description, event_date, requested_by),
        )
        db.commit()
    logger.info(f"Event '{event_name}' requested successfully by user_id: {requested_by}")
    cache_delete_events()
    return redirect(url_for("events"))


@app.route("/approve_event/<int:event_id>", methods=["POST"])
@login_required
@admin_or_manager_required
def approve_event(event_id):

    if not event_id:
        logger.info("Event ID not provided")
        return jsonify(error="Event ID not provided."), 400

    db = get_db()
    approver = session["user_id"]

    with db.cursor() as cursor:
        cursor.execute(
            "UPDATE events SET approved_by = %s WHERE event_id = %s",
            (approver, event_id),
        )
        db.commit()
    logger.info("Event approved successfully")
    cache_delete_events()
    return jsonify(success=True), 200


@app.route("/api/tasks/<int:task_id>", methods=["PATCH"])
@login_required
def complete_task(task_id):
    if not task_id:
        logger.info("Task ID not provided")
        return jsonify(error="Task ID not provided."), 400

    db = get_db()
    status = "Completed"
    with db.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            "SELECT deadline FROM tasks WHERE task_id = %s AND assigned_to = %s",
            (task_id, session["user_id"]),
        )
        result = cursor.fetchone()
        if not result:
            logger.info(f"Task ID {task_id} not found or not assigned to user.")
            return jsonify(error="Task not found or not assigned to you."), 404
        if result["deadline"] < datetime.now().date():
            logger.info(f"Task ID {task_id} deadline has passed.")
            status = "Failed"
            logger.info("Task deadline has passed.")
    with db.cursor() as cursor:
        cursor.execute(
            "UPDATE tasks SET status = %s WHERE task_id = %s",
            (
                status,
                task_id,
            ),
        )
        db.commit()
    if status == "Completed":
        logger.info(f"Task {task_id} marked as Completed successfully.")
        cache_delete_projects_tasks()
        return jsonify(success=True), 200

    else:
        logger.info(f"Task {task_id} marked as Failed because deadline passed.")
        return jsonify(error="Task deadline has passed."), 400


@app.route("/api/events", methods=["GET"])
@user_cache(base_key="events-json")
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


@app.route("/analysis", methods=["GET"])
@user_cache(base_key="analysis-html")
@login_required
@admin_or_manager_required
def analysis():

    db = get_db()
    projects_data = []
    with db.cursor(cursor_factory=RealDictCursor) as cursor:

        cursor.execute(
            """
            SELECT p.project_id, p.project_name, p.start_date, p.end_date,
                   t.task_id, t.task_name, t.deadline, t.status, t.normal_duration, t.crash_duration,
                   t.normal_cost, t.crash_cost
            FROM projects p
            LEFT JOIN tasks t ON p.project_id = t.project_id
            WHERE t.task_id IS NOT NULL
            ORDER BY p.project_id, t.deadline ASC;
        """
        )
        rows = cursor.fetchall()

        current_project_id = None
        project_tasks = []
        for row in rows:
            if row["project_id"] != current_project_id:
                if current_project_id is not None and project_tasks:
                    projects_data[-1]["tasks"] = project_tasks
                projects_data.append(
                    {
                        "project_id": row["project_id"],
                        "project_name": row["project_name"],
                        "start_date": row["start_date"],
                        "end_date": row["end_date"],
                        "tasks": [],
                    }
                )
                current_project_id = row["project_id"]
                project_tasks = []

            project_tasks.append(
                {
                    "task_id": row["task_id"],
                    "task_name": row["task_name"],
                    "deadline": row["deadline"],
                    "status": row["status"],
                    "normal_duration": row["normal_duration"],
                    "crash_duration": row["crash_duration"],
                    "normal_cost": row["normal_cost"],
                    "crash_cost": row["crash_cost"],
                }
            )

        if projects_data and project_tasks:
            projects_data[-1]["tasks"] = project_tasks

    projects_data = [p for p in projects_data if p.get("tasks")]

    return render_template("analysis.html", projects_data=projects_data)


@app.route("/about", methods=["GET"])
@cache_static
def about():
    return render_template("about.html")


@app.teardown_appcontext
def shutdown_appcontext(exception=None):
    close_db()


if __name__ == "__main__":
    app.run(debug=True, port=5000)
