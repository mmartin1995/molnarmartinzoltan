# C:\MyProjects\molnarmartinzoltan\valasztasvisszaszamlalo\app.py
from flask import Blueprint, render_template
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

valasztas_blueprint = Blueprint("visszaszamlalo", __name__)

TARGET_TZ = ZoneInfo("Europe/Budapest")
TARGET_DT = datetime(2026, 4, 12, 6, 0, 0, tzinfo=TARGET_TZ)

@valasztas_blueprint.route("/")
def index():
    target_epoch_ms = int(TARGET_DT.timestamp() * 1000)
    server_now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    return render_template(
        "htmls/visszaszamlalo.html",  # lásd a 2. pontot
        target_epoch_ms=target_epoch_ms,
        server_now_ms=server_now_ms,
        target_tz="Europe/Budapest",
        target_str="2026.04.12. 06:00",
    )
