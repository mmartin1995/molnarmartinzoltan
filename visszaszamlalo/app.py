# C:\MyProjects\molnarmartinzoltan\visszaszamlalo\app.py
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict

import requests
from flask import (
    Blueprint,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import (
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from sqlalchemy import func
from werkzeug.security import check_password_hash, generate_password_hash

from .models import db, User, Project, Counter

# ----------------------------------------------------------------------
# Blueprint létrehozása (külön template/static mappákkal)
# ----------------------------------------------------------------------
visszaszamlalo_blueprint = Blueprint(
    "visszaszamlalo",
    __name__,
    template_folder="htmls",
    static_folder="static",
)

# ----------------------------------------------------------------------
# Auth/DB init – ezt a gyökér app.py hívja meg: init_auth(app)
# ----------------------------------------------------------------------
def init_auth(app):
    """SQLAlchemy + Flask-Login inicializálása, táblák létrehozása."""
    db.init_app(app)
    login_manager = LoginManager(app)
    login_manager.login_view = "visszaszamlalo.login"

    @login_manager.user_loader
    def load_user(user_id: str):
        try:
            return User.query.get(int(user_id))
        except Exception:
            return None

    # Táblák létrehozása (első induláskor)
    with app.app_context():
        db.create_all()


# ----------------------------------------------------------------------
# Segédfüggvények / szerializálók
# ----------------------------------------------------------------------
def is_admin() -> bool:
    return current_user.is_authenticated and getattr(current_user, "role", "") == "admin"


def admin_guard():
    if not is_admin():
        abort(403)


def serialize_project(p: Project) -> Dict[str, Any]:
    return {"id": p.id, "name": p.name, "color": p.color, "font": p.font}


def serialize_counter(c: Counter) -> Dict[str, Any]:
    return {
        "id": c.id,
        "name": c.name,
        "deadline": c.deadline,
        "projectId": c.project_id,
        "archived": c.archived,
        "createdAt": c.created_at,
        "order": c.order,
    }


# ----------------------------------------------------------------------
# Első admin setup – csak akkor elérhető, ha még nincs felhasználó
# ----------------------------------------------------------------------
@visszaszamlalo_blueprint.route("/setup", methods=["GET", "POST"])
def setup():
    user_count = db.session.query(func.count(User.id)).scalar() or 0
    if user_count > 0:
        # Ha már van user, irány a login
        return redirect(url_for("visszaszamlalo.login"))

    error = None
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        password2 = request.form.get("password2") or ""
        if not username or not password:
            error = "Felhasználónév és jelszó kötelező."
        elif password != password2:
            error = "A jelszavak nem egyeznek."
        elif User.query.filter_by(username=username).first():
            error = "Ilyen felhasználó már létezik."
        else:
            u = User(username=username, password_hash=generate_password_hash(password), role="admin")
            db.session.add(u)
            db.session.commit()
            # Első admin kész → login oldal
            return redirect(url_for("visszaszamlalo.login"))

    return render_template("visszaszamlalo_setup.html", error=error)


# ----------------------------------------------------------------------
# Bejelentkezés / kijelentkezés
# ----------------------------------------------------------------------
@visszaszamlalo_blueprint.route("/login", methods=["GET", "POST"])
def login():
    # Ha még nincs user, kényszerítsük a /setup-ra
    user_count = db.session.query(func.count(User.id)).scalar() or 0
    if user_count == 0:
        return redirect(url_for("visszaszamlalo.setup"))

    error = None
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        u = User.query.filter_by(username=username).first()
        if u and check_password_hash(u.password_hash, password):
            login_user(u)
            # Admin → admin felület, user → megtekintő
            if u.role == "admin":
                return redirect(url_for("visszaszamlalo.admin_index"))
            return redirect(url_for("visszaszamlalo.index"))
        error = "Hibás felhasználónév vagy jelszó."

    return render_template("visszaszamlalo_login.html", error=error)


@visszaszamlalo_blueprint.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("visszaszamlalo.login"))


# ----------------------------------------------------------------------
# Megtekintő (mindkét szerep), de login kötelező
# READ_ONLY = True, az admin UI el van rejtve
# ----------------------------------------------------------------------
@visszaszamlalo_blueprint.route("/")
@login_required
def index():
    projects = [serialize_project(p) for p in Project.query.order_by(Project.name).all()]
    counters = [serialize_counter(c) for c in Counter.query.all()]
    initial = {"projects": projects, "counters": counters}
    return render_template(
        "visszaszamlalo.html",
        READ_ONLY=True,
        INITIAL_DATA=json.dumps(initial, ensure_ascii=False),
        target_tz="Europe/Budapest",
        target_str="Megtekintés",
    )


# ----------------------------------------------------------------------
# Admin felület – csak adminnak
# READ_ONLY = False, szerkesztés engedélyezve
# ----------------------------------------------------------------------
@visszaszamlalo_blueprint.route("/admin")
@login_required
def admin_index():
    admin_guard()
    projects = [serialize_project(p) for p in Project.query.order_by(Project.name).all()]
    counters = [serialize_counter(c) for c in Counter.query.all()]
    initial = {"projects": projects, "counters": counters}
    return render_template(
        "visszaszamlalo.html",
        READ_ONLY=False,
        INITIAL_DATA=json.dumps(initial, ensure_ascii=False),
        target_tz="Europe/Budapest",
        target_str="Admin",
    )


# ----------------------------------------------------------------------
# Opcionális: külön felhasználókezelő admin oldal (HTML)
# ----------------------------------------------------------------------
@visszaszamlalo_blueprint.route("/admin/users")
@login_required
def admin_users_page():
    admin_guard()
    return render_template("visszaszamlalo_users.html")


# ----------------------------------------------------------------------
# ICS URL-proxy – csak adminnak (CORS-kímélő)
# ----------------------------------------------------------------------
_HTTP_URL_RE = re.compile(r"^https?://", re.I)
_MAX_ICS_BYTES = 3_000_000  # 3 MB


@visszaszamlalo_blueprint.route("/api/ics_proxy")
@login_required
def api_ics_proxy():
    admin_guard()
    url = (request.args.get("url") or "").strip()
    if not url or not _HTTP_URL_RE.match(url):
        return ("Invalid URL", 400)

    try:
        r = requests.get(
            url,
            headers={"User-Agent": "Visszaszamlalo/1.0 (+https://molnarmartinzoltan.hu)"},
            timeout=15,
            stream=True,
        )
        r.raise_for_status()

        size = 0
        chunks = []
        for chunk in r.iter_content(8192):
            size += len(chunk)
            if size > _MAX_ICS_BYTES:
                return ("ICS túl nagy", 413)
            chunks.append(chunk)
        data = b"".join(chunks)

        # Sok szolgáltató rossz CT-t ad, nem fail-eljünk emiatt
        return (data, 200, {"Content-Type": "text/calendar; charset=utf-8"})
    except requests.RequestException as e:
        return (f"Hiba az ICS letöltés közben: {e}", 502)


# ----------------------------------------------------------------------
# API-k – minden API login-köteles; az író műveletek csak adminnak
# ----------------------------------------------------------------------
# Projektek
@visszaszamlalo_blueprint.route("/api/projects")
@login_required
def api_projects():
    rows = Project.query.order_by(Project.name).all()
    return jsonify([serialize_project(p) for p in rows])


@visszaszamlalo_blueprint.route("/api/project", methods=["POST"])
@login_required
def api_project_create():
    admin_guard()
    b = request.get_json(force=True)
    pid = (b.get("id") or "").strip()
    if not pid:
        return jsonify({"ok": False, "error": "project.id kötelező"}), 400
    if Project.query.get(pid):
        return jsonify({"ok": False, "error": "Már létezik ilyen projekt"}), 409
    p = Project(
        id=pid,
        name=b.get("name") or "Névtelen",
        color=b.get("color") or "#6ea8fe",
        font=b.get("font") or "default",
    )
    db.session.add(p)
    db.session.commit()
    return jsonify({"ok": True})


@visszaszamlalo_blueprint.route("/api/project/<pid>", methods=["PUT", "DELETE"])
@login_required
def api_project_update(pid: str):
    admin_guard()
    p = Project.query.get_or_404(pid)
    if request.method == "DELETE":
        # projekt törlésekor a számlálók project_id-je NULL-ra áll
        Counter.query.filter_by(project_id=pid).update({"project_id": None})
        db.session.delete(p)
        db.session.commit()
        return jsonify({"ok": True})

    patch = request.get_json(force=True)
    for k in ("name", "color", "font"):
        if k in patch:
            setattr(p, k, patch[k] or getattr(p, k))
    db.session.commit()
    return jsonify({"ok": True})


# Számlálók
@visszaszamlalo_blueprint.route("/api/counters")
@login_required
def api_counters():
    rows = Counter.query.all()
    return jsonify([serialize_counter(c) for c in rows])


@visszaszamlalo_blueprint.route("/api/counter", methods=["POST"])
@login_required
def api_counter_create():
    admin_guard()
    b = request.get_json(force=True)
    cid = (b.get("id") or "").strip()
    if not cid:
        return jsonify({"ok": False, "error": "counter.id kötelező"}), 400
    if Counter.query.get(cid):
        return jsonify({"ok": False, "error": "Már létezik ilyen számláló"}), 409

    c = Counter(
        id=cid,
        name=b.get("name") or "Névtelen",
        deadline=b.get("deadline") or int(datetime.now(timezone.utc).timestamp() * 1000),
        project_id=b.get("projectId"),
        archived=bool(b.get("archived", False)),
        created_at=b.get("createdAt") or int(datetime.now(timezone.utc).timestamp() * 1000),
        order=int(b.get("order") or 0),
    )
    db.session.add(c)
    db.session.commit()
    return jsonify({"ok": True})


@visszaszamlalo_blueprint.route("/api/counter/<cid>", methods=["PUT", "DELETE"])
@login_required
def api_counter_update(cid: str):
    admin_guard()
    c = Counter.query.get_or_404(cid)
    if request.method == "DELETE":
        db.session.delete(c)
        db.session.commit()
        return jsonify({"ok": True})

    patch = request.get_json(force=True)
    if "name" in patch:
        c.name = patch["name"] or c.name
    if "deadline" in patch:
        c.deadline = int(patch["deadline"])
    if "projectId" in patch:
        c.project_id = patch["projectId"]
    if "archived" in patch:
        c.archived = bool(patch["archived"])
    if "createdAt" in patch:
        c.created_at = int(patch["createdAt"])
    if "order" in patch:
        c.order = int(patch["order"])
    db.session.commit()
    return jsonify({"ok": True})


# ----------------------------------------------------------------------
# Admin – felhasználókezelés API (ha használod az admin/users oldalt)
# ----------------------------------------------------------------------
@visszaszamlalo_blueprint.route("/api/users", methods=["GET"])
@login_required
def api_users_list():
    admin_guard()
    rows = User.query.order_by(User.id).all()
    return jsonify([{"id": u.id, "username": u.username, "role": u.role} for u in rows])


@visszaszamlalo_blueprint.route("/api/users", methods=["POST"])
@login_required
def api_users_create():
    admin_guard()
    b = request.get_json(force=True)
    username = (b.get("username") or "").strip()
    password = b.get("password") or ""
    role = b.get("role") or "user"
    if not username or not password:
        return jsonify({"ok": False, "error": "username/password kötelező"}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"ok": False, "error": "Már létezik ilyen felhasználó"}), 409
    u = User(username=username, password_hash=generate_password_hash(password), role=role)
    db.session.add(u)
    db.session.commit()
    return jsonify({"ok": True, "id": u.id})


@visszaszamlalo_blueprint.route("/api/users/<int:uid>", methods=["PUT", "DELETE"])
@login_required
def api_users_update(uid: int):
    admin_guard()
    u = User.query.get_or_404(uid)

    if request.method == "DELETE":
        if u.role == "admin" and User.query.filter_by(role="admin").count() <= 1:
            return jsonify({"ok": False, "error": "Az utolsó admin nem törölhető"}), 400
        db.session.delete(u)
        db.session.commit()
        return jsonify({"ok": True})

    b = request.get_json(force=True)
    if "username" in b:
        name = (b["username"] or "").strip()
        if not name:
            return jsonify({"ok": False, "error": "username nem lehet üres"}), 400
        if User.query.filter(User.username == name, User.id != uid).first():
            return jsonify({"ok": False, "error": "Felhasználónév már foglalt"}), 409
        u.username = name
    if "role" in b:
        u.role = b["role"] or u.role
    if "password" in b and b["password"]:
        u.password_hash = generate_password_hash(b["password"])
    db.session.commit()
    return jsonify({"ok": True})
