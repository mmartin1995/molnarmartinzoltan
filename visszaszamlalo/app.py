# visszaszamlalo/app.py
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, abort
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import json

from .models import db, User, Project, Counter

visszaszamlalo_blueprint = Blueprint(
    "visszaszamlalo", __name__,
)

TARGET_TZ = ZoneInfo("Europe/Budapest")

def init_auth(app):
    # DB és Login init
    db.init_app(app)
    login_manager = LoginManager(app)
    login_manager.login_view = "visszaszamlalo.login"

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # első indításkor létrehozunk mindent + egy alap admint
    with app.app_context():
        db.create_all()
        if not User.query.first():
            admin = User(username="admin", password_hash=generate_password_hash("admin123"), role="admin")
            db.session.add(admin)
            prj = Project(id="prj_default", name="Alap", color="#6ea8fe", font="default")
            db.session.add(prj)
            dt = datetime(2026,4,12,6,0,0,tzinfo=TARGET_TZ)
            ctr = Counter(
                id="ctr_sample",
                name="Mintaszámláló – 2026.04.12. 06:00",
                deadline=int(dt.timestamp()*1000),
                project=prj,
                archived=False,
                created_at=int(datetime.now(timezone.utc).timestamp()*1000),
                order=0
            )
            db.session.add(ctr)
            db.session.commit()

def is_admin():
    return current_user.is_authenticated and getattr(current_user, "role", "") == "admin"

def serialize_project(p: Project):
    return {"id": p.id, "name": p.name, "color": p.color, "font": p.font}

def serialize_counter(c: Counter):
    return {"id": c.id, "name": c.name, "deadline": c.deadline, "projectId": c.project_id,
            "archived": c.archived, "createdAt": c.created_at, "order": c.order}

# -------- Oldalak --------
@visszaszamlalo_blueprint.route("/")
def public_index():
    projects = [serialize_project(p) for p in Project.query.order_by(Project.name).all()]
    counters = [serialize_counter(c) for c in Counter.query.all()]
    initial = {"projects": projects, "counters": counters}
    return render_template(
        "htmls/visszaszamlalo.html",
        READ_ONLY=True,
        INITIAL_DATA=json.dumps(initial, ensure_ascii=False),
        target_tz="Europe/Budapest",
        target_str="Publikus"
    )

@visszaszamlalo_blueprint.route("/admin")
@login_required
def admin_index():
    if not is_admin():
        abort(403)
    projects = [serialize_project(p) for p in Project.query.order_by(Project.name).all()]
    counters = [serialize_counter(c) for c in Counter.query.all()]
    initial = {"projects": projects, "counters": counters}
    return render_template(
        "htmls/visszaszamlalo.html",
        READ_ONLY=False,
        INITIAL_DATA=json.dumps(initial, ensure_ascii=False),
        target_tz="Europe/Budapest",
        target_str="Admin"
    )

# -------- Auth --------
@visszaszamlalo_blueprint.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        u = User.query.filter_by(username=request.form.get("username","").strip()).first()
        if u and check_password_hash(u.password_hash, request.form.get("password","")):
            login_user(u)
            return redirect(url_for("visszaszamlalo.admin_index"))
        return render_template("htmls/visszaszamlalo_login.html", error="Hibás felhasználónév vagy jelszó.")
    return render_template("htmls/visszaszamlalo_login.html")

@visszaszamlalo_blueprint.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("visszaszamlalo.public_index"))

# -------- API: olvasás mindenkinek --------
@visszaszamlalo_blueprint.route("/api/projects")
def api_projects():
    return jsonify([serialize_project(p) for p in Project.query.all()])

@visszaszamlalo_blueprint.route("/api/counters")
def api_counters():
    return jsonify([serialize_counter(c) for c in Counter.query.all()])

# -------- API: módosítás (csak admin) --------
def admin_guard():
    if not is_admin():
        abort(403)

@visszaszamlalo_blueprint.route("/api/project", methods=["POST"])
def api_project_create():
    admin_guard()
    b = request.get_json(force=True)
    p = Project(id=b["id"], name=b["name"], color=b.get("color","#6ea8fe"), font=b.get("font","default"))
    db.session.add(p); db.session.commit()
    return jsonify({"ok": True})

@visszaszamlalo_blueprint.route("/api/project/<pid>", methods=["PUT","DELETE"])
def api_project_update(pid):
    admin_guard()
    p = Project.query.get_or_404(pid)
    if request.method == "DELETE":
        Counter.query.filter_by(project_id=pid).update({"project_id": None})
        db.session.delete(p); db.session.commit()
        return jsonify({"ok": True})
    patch = request.get_json(force=True)
    for k in ("name","color","font"):
        if k in patch: setattr(p, k, patch[k])
    db.session.commit()
    return jsonify({"ok": True})

@visszaszamlalo_blueprint.route("/api/counter", methods=["POST"])
def api_counter_create():
    admin_guard()
    b = request.get_json(force=True)
    c = Counter(
        id=b["id"], name=b["name"], deadline=b["deadline"],
        project_id=b.get("projectId"), archived=b.get("archived", False),
        created_at=b.get("createdAt"), order=b.get("order", 0)
    )
    db.session.add(c); db.session.commit()
    return jsonify({"ok": True})

@visszaszamlalo_blueprint.route("/api/counter/<cid>", methods=["PUT","DELETE"])
def api_counter_update(cid):
    admin_guard()
    c = Counter.query.get_or_404(cid)
    if request.method == "DELETE":
        db.session.delete(c); db.session.commit()
        return jsonify({"ok": True})
    patch = request.get_json(force=True)
    if "name" in patch: c.name = patch["name"]
    if "deadline" in patch: c.deadline = patch["deadline"]
    if "projectId" in patch: c.project_id = patch["projectId"]
    if "archived" in patch: c.archived = patch["archived"]
    if "createdAt" in patch: c.created_at = patch["createdAt"]
    if "order" in patch: c.order = patch["order"]
    db.session.commit()
    return jsonify({"ok": True})
