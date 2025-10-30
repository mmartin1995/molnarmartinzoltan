# visszaszamlalo/app.py
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, abort
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from sqlalchemy import func
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import json

from .models import db, User, Project, Counter

visszaszamlalo_blueprint = Blueprint("visszaszamlalo", __name__)
TARGET_TZ = ZoneInfo("Europe/Budapest")

# ---- helper ----
def is_admin():
    return current_user.is_authenticated and getattr(current_user, "role", "") == "admin"

def admin_guard():
    if not is_admin():
        abort(403)

def serialize_project(p: Project):
    return {"id": p.id, "name": p.name, "color": p.color, "font": p.font}

def serialize_counter(c: Counter):
    return {"id": c.id, "name": c.name, "deadline": c.deadline, "projectId": c.project_id,
            "archived": c.archived, "createdAt": c.created_at, "order": c.order}

# ---- auth+db init hívva a gyökér app.py-ból: init_auth(app) ----
def init_auth(app):
    db.init_app(app)
    login_manager = LoginManager(app)
    login_manager.login_view = "visszaszamlalo.login"

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    with app.app_context():
        db.create_all()

# ---- első admin setup (csak ha nincs még user) ----
@visszaszamlalo_blueprint.route("/setup", methods=["GET","POST"])
def setup():
    user_count = db.session.query(func.count(User.id)).scalar() or 0
    if user_count > 0:
        return redirect(url_for("visszaszamlalo.login"))

    error = None
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","")
        password2 = request.form.get("password2","")
        if not username or not password:
            error = "Felhasználónév és jelszó kötelező."
        elif password != password2:
            error = "A jelszavak nem egyeznek."
        elif User.query.filter_by(username=username).first():
            error = "Ilyen felhasználó már létezik."
        else:
            u = User(username=username, password_hash=generate_password_hash(password), role="admin")
            db.session.add(u)

            # kezdeti minta-adatok is jöhetnek
            if not Project.query.first():
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
            # első admin létrehozva → login oldal
            return redirect(url_for("visszaszamlalo.login"))

    return render_template("htmls/visszaszamlalo_setup.html", error=error)

# ---- be/kijelentkezés ----
@visszaszamlalo_blueprint.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","")
        u = User.query.filter_by(username=username).first()
        if u and check_password_hash(u.password_hash, password):
            login_user(u)
            # admin → admin felület, user → nézet
            return redirect(url_for("visszaszamlalo.admin_index" if u.role=="admin" else "visszaszamlalo.index"))
        return render_template("htmls/visszaszamlalo_login.html", error="Hibás felhasználónév vagy jelszó.")
    return render_template("htmls/visszaszamlalo_login.html")

@visszaszamlalo_blueprint.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("visszaszamlalo.login"))

# ---- számlálók megtekintése: LOGIN KÖTELEZŐ, mindig READ_ONLY ----
@visszaszamlalo_blueprint.route("/")
@login_required
def index():
    projects = [serialize_project(p) for p in Project.query.order_by(Project.name).all()]
    counters = [serialize_counter(c) for c in Counter.query.all()]
    initial = {"projects": projects, "counters": counters}
    return render_template(
        "htmls/visszaszamlalo.html",
        READ_ONLY=True,                       # <- mindig csak nézet
        INITIAL_DATA=json.dumps(initial, ensure_ascii=False),
        target_tz="Europe/Budapest",
        target_str="Megtekintés"
    )

# ---- admin felület (szerkesztés) ----
@visszaszamlalo_blueprint.route("/admin")
@login_required
def admin_index():
    admin_guard()
    projects = [serialize_project(p) for p in Project.query.order_by(Project.name).all()]
    counters = [serialize_counter(c) for c in Counter.query.all()]
    initial = {"projects": projects, "counters": counters}
    return render_template(
        "htmls/visszaszamlalo.html",
        READ_ONLY=False,                      # <- adminnál szerkeszthető UI
        INITIAL_DATA=json.dumps(initial, ensure_ascii=False),
        target_tz="Europe/Budapest",
        target_str="Admin"
    )

# ---- felhasználókezelő admin oldal (opcionális külön UI) ----
@visszaszamlalo_blueprint.route("/admin/users")
@login_required
def admin_users_page():
    admin_guard()
    return render_template("htmls/visszaszamlalo_users.html")

# ---- API-k: mostantól MINDEN API legalább loginhoz kötött ----
@visszaszamlalo_blueprint.route("/api/projects")
@login_required
def api_projects():
    rows = Project.query.all()
    return jsonify([serialize_project(p) for p in rows])

@visszaszamlalo_blueprint.route("/api/counters")
@login_required
def api_counters():
    rows = Counter.query.all()
    return jsonify([serialize_counter(c) for c in rows])

# módosító API-k: csak admin
@visszaszamlalo_blueprint.route("/api/project", methods=["POST"])
@login_required
def api_project_create():
    admin_guard()
    b = request.get_json(force=True)
    p = Project(id=b["id"], name=b["name"], color=b.get("color","#6ea8fe"), font=b.get("font","default"))
    db.session.add(p); db.session.commit()
    return jsonify({"ok": True})

@visszaszamlalo_blueprint.route("/api/project/<pid>", methods=["PUT","DELETE"])
@login_required
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
@login_required
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
@login_required
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

# ---- USER API-k adminnak (ha kell az admin felhasználókezelő oldalhoz) ----
@visszaszamlalo_blueprint.route("/api/users", methods=["GET"])
@login_required
def api_users_list():
    admin_guard()
    rows = User.query.order_by(User.id).all()
    return jsonify([{"id":u.id, "username":u.username, "role":u.role} for u in rows])

@visszaszamlalo_blueprint.route("/api/users", methods=["POST"])
@login_required
def api_users_create():
    admin_guard()
    b = request.get_json(force=True)
    username = (b.get("username") or "").strip()
    password = b.get("password") or ""
    role = b.get("role") or "user"
    if not username or not password:
        return jsonify({"ok": False, "error":"username/password kötelező"}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"ok": False, "error":"Már létezik ilyen felhasználó"}), 409
    u = User(username=username, password_hash=generate_password_hash(password), role=role)
    db.session.add(u); db.session.commit()
    return jsonify({"ok": True, "id": u.id})

@visszaszamlalo_blueprint.route("/api/users/<int:uid>", methods=["PUT","DELETE"])
@login_required
def api_users_update(uid):
    admin_guard()
    u = User.query.get_or_404(uid)
    if request.method == "DELETE":
        if u.role == "admin" and User.query.filter_by(role="admin").count() <= 1:
            return jsonify({"ok": False, "error":"Az utolsó admin nem törölhető"}), 400
        db.session.delete(u); db.session.commit()
        return jsonify({"ok": True})

    b = request.get_json(force=True)
    if "username" in b:
        name = (b["username"] or "").strip()
        if not name: return jsonify({"ok": False, "error":"username nem lehet üres"}), 400
        if User.query.filter(User.username==name, User.id!=uid).first():
            return jsonify({"ok": False, "error":"Felhasználónév már foglalt"}), 409
        u.username = name
    if "role" in b: u.role = b["role"]
    if "password" in b and b["password"]:
        u.password_hash = generate_password_hash(b["password"])
    db.session.commit()
    return jsonify({"ok": True})
