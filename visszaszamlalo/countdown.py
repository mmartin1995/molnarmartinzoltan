# countdown.py — több számlálós, tartós verzió PROJEKTEKKEL + PROJEKT SZŰRŐVEL
# + Bal oldali oldalsáv: Új számláló / Stílus / Naptárak / Projektek
# + QSplitter: bal sáv és fő rész aránya egérrel állítható (mentés/visszaállítás)
# + KERET NÉLKÜLI ÁTMÉRETEZÉS: bal/jobb/felső/alsó széleken húzható
# + Ablakpozíció megjegyzése
# + Stílus ablak: Átlátszóság + Default betűtípus + Betűméretek (cím/név/számláló/info/gomb) — mentve
# + ICS NAPTÁR (több .ics), dupla katt → előtöltött létrehozás
# + Másodperchez igazított frissítés, drag&drop, auto-magasság tálcáig
# + Duplakatt szerkesztés (név/idő/projekt), projekt stílus (szín + font)
# + „Új projekt…” gomb közvetlenül a Számláló dialógusban
# + Archiválás gomb soronként + „Archiváltak megjelenítése” kapcsoló
# + Rendezés – Manuális / Projekt szerint / Lejárat növ. / Lejárat csökk.
# pip install PySide6
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo
from typing import Optional, Dict, Any, List, Tuple
from uuid import uuid4
import os, json
from pathlib import Path
import urllib.request
import ssl

from PySide6.QtCore import Qt, QTimer, QPoint, Signal, QSize, QDateTime, QRect
from PySide6.QtGui import (
    QPainter, QColor, QFont, QGuiApplication, QCursor, QIcon, QPixmap, QPen, QAction
)
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton,
    QFrame, QLineEdit, QDateTimeEdit, QDialog, QDialogButtonBox,
    QMessageBox, QSizePolicy, QListWidget, QListWidgetItem,
    QAbstractScrollArea, QAbstractItemView, QColorDialog,
    QComboBox, QFontComboBox, QSlider, QCheckBox, QMenu, QSplitter,
    QSpinBox, QAbstractSpinBox
)

# ========= UI =========
@dataclass
class UIConfig:
    font_family: str = "Segoe UI"
    font_size_title: int = 20
    font_size_name: int = 16
    font_size_counter: int = 32
    font_size_info: int = 13
    font_size_button: int = 18
    button_height: int = 56
    padding_v: int = 8
    padding_h: int = 16
    window_width: int = 900
    window_height: int = 520
    bg_opacity: float = 0.70

UI = UIConfig()
# ======================

APP_NAME = "mmz_countdown"
TARGET_TZ = ZoneInfo("Europe/Budapest")

def _data_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path.home()
    d = base / (APP_NAME if os.name == "nt" else f".{APP_NAME}")
    d.mkdir(parents=True, exist_ok=True)
    return d

DATA_FILE = _data_dir() / "counters.json"

def _build_style_dict_from_UI() -> dict:
    return {
        "font_family": UI.font_family,
        "font_sizes": {
            "title": UI.font_size_title,
            "name": UI.font_size_name,
            "counter": UI.font_size_counter,
            "info": UI.font_size_info,
            "button": UI.font_size_button,
        }
    }

def _apply_style_to_UI_from_data(data: Dict[str, Any]) -> None:
    style = data.get("style", {})
    ff = style.get("font_family")
    if ff:
        UI.font_family = ff
    fs = style.get("font_sizes", {})
    UI.font_size_title   = int(fs.get("title", UI.font_size_title))
    UI.font_size_name    = int(fs.get("name", UI.font_size_name))
    UI.font_size_counter = int(fs.get("counter", UI.font_size_counter))
    UI.font_size_info    = int(fs.get("info", UI.font_size_info))
    UI.font_size_button  = int(fs.get("button", UI.font_size_button))

def load_data() -> Dict[str, Any]:
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "counters" in data:
                    data.setdefault("mode", "dark")
                    data.setdefault("projects", [])
                    data.setdefault("ics", {})
                    data.setdefault("opacity", UI.bg_opacity)
                    data.setdefault("window_pos", None)
                    data.setdefault("show_archived", False)
                    data.setdefault("sort_mode", "manual")
                    data.setdefault("splitter_sizes", None)
                    data.setdefault("style", _build_style_dict_from_UI())
                    for c in data.get("counters", []):
                        c.setdefault("archived", False)
                    ics = data["ics"]
                    if isinstance(ics, dict):
                        url = ics.get("url")
                        if url and not ics.get("calendars"):
                            cal = {"id": uuid4().hex, "name": "Google naptár", "url": url, "enabled": True}
                            ics["calendars"] = [cal]
                            ics.pop("url", None)
                        ics.setdefault("calendars", [])
                        ics.setdefault("use_end_time", False)
                        ics.setdefault("all_day_time", "09:00")
                    _apply_style_to_UI_from_data(data)
                    return data
        except Exception:
            pass
    data = {
        "version": 1,
        "timezone": "Europe/Budapest",
        "mode": "dark",
        "projects": [],
        "counters": [],
        "ics": {"calendars": [], "use_end_time": False, "all_day_time": "09:00"},
        "opacity": UI.bg_opacity,
        "window_pos": None,
        "show_archived": False,
        "sort_mode": "manual",
        "splitter_sizes": None,
        "style": _build_style_dict_from_UI(),
    }
    return data

def save_data(data: Dict[str, Any]) -> None:
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        msg = QMessageBox(QMessageBox.Icon.Warning, "Mentési hiba",
                          f"Nem sikerült menteni:\n{e}")
        msg.exec()

# ---- Szín segéd ----
def qcolor_to_hex8(c: QColor) -> str:
    return f"#{c.red():02X}{c.green():02X}{c.blue():02X}{c.alpha():02X}"

def hex_to_qcolor(s: Optional[str]) -> Optional[QColor]:
    if not s: return None
    t = s.strip().lstrip("#")
    try:
        if len(t) == 8:
            r = int(t[0:2], 16); g = int(t[2:4], 16); b = int(t[4:6], 16); a = int(t[6:8], 16)
            return QColor(r, g, b, a)
        elif len(t) == 6:
            r = int(t[0:2], 16); g = int(t[2:4], 16); b = int(t[4:6], 16)
            return QColor(r, g, b, 255)
    except Exception:
        return None
    return None

def qcolor_to_css_rgba(c: QColor) -> str:
    return f"rgba({c.red()},{c.green()},{c.blue()},{c.alpha()})"

def color_swatch_icon(c: QColor, size: int = 14) -> QIcon:
    pm = QPixmap(size, size); pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm); p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setBrush(c); p.setPen(QPen(QColor(0, 0, 0, 60))); r = 2
    p.drawRoundedRect(0, 0, size - 1, size - 1, r, r); p.end()
    return QIcon(pm)

# ---- Gomb stílus ----
def make_btn_style(fg: str) -> str:
    return f"""
    QPushButton {{
        color: {fg};
        background-color: transparent;
        border: 1px solid transparent;
        padding: {UI.padding_v}px {UI.padding_h}px;
        font-size: {UI.font_size_button}px;
    }}
    QPushButton:hover {{
        background-color: transparent;
        border: 1px solid transparent;
    }}
    QPushButton:pressed, QPushButton:checked {{
        background-color: transparent;
        border: 1px solid transparent;
    }}
    QPushButton:focus {{
        outline: none;
        border: 1px solid transparent;
    }}
    """

# ---------- Projektek ----------
class ProjectEditorDialog(QDialog):
    def __init__(self, parent=None, name: str = "", color_hex: Optional[str] = None, font_family: Optional[str] = None):
        super().__init__(parent)
        self.setWindowTitle("Projekt szerkesztése")
        self.setModal(True)
        self._color = hex_to_qcolor(color_hex) or QColor(0, 0, 0, 96)
        self._font_family = font_family or UI.font_family

        layout = QVBoxLayout(self)
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Projekt neve:"))
        self.name_edit = QLineEdit(); self.name_edit.setText(name); row1.addWidget(self.name_edit)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Háttérszín:"))
        self.color_btn = QPushButton("Szín választása"); self.color_btn.setIcon(color_swatch_icon(self._color))
        self.color_btn.clicked.connect(self.pick_color); row2.addWidget(self.color_btn)
        layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Betűtípus:"))
        self.font_combo = QFontComboBox(); self.font_combo.setCurrentFont(QFont(self._font_family)); row3.addWidget(self.font_combo)
        layout.addLayout(row3)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject); layout.addWidget(btns)

        self.apply_theme(getattr(parent, "mode", "dark"))

    def apply_theme(self, mode: str):
        if mode == "dark":
            fg = "#FFFFFF"; bg = "#121212"; input_bg = "#1E1E1E"; border = "#3A3A3A"
        else:
            fg = "#000000"; bg = "#FFFFFF"; input_bg = "#FFFFFF"; border = "#C8C8C8"
        self.setStyleSheet(f"""
            QDialog, QWidget {{ background-color: {bg}; color: {fg}; }}
            QLineEdit {{ background-color: {input_bg}; color: {fg}; border: 1px solid {border}; }}
            QFontComboBox {{ background-color: {input_bg}; color: {fg}; border: 1px solid {border}; }}
            QPushButton {{ color: {fg}; background-color: transparent; border: 1px solid transparent; }}
            QListWidget {{ background-color: {bg}; color: {fg}; border: 1px solid {border}; }}
        """)

    def pick_color(self):
        dlg = QColorDialog(self)
        dlg.setOption(QColorDialog.ColorDialogOption.ShowAlphaChannel, True)
        dlg.setCurrentColor(self._color)
        if dlg.exec():
            self._color = dlg.selectedColor()
            self.color_btn.setIcon(color_swatch_icon(self._color))

    def get_values(self) -> Optional[dict]:
        name = (self.name_edit.text() or "").strip()
        if not name:
            QMessageBox.warning(self, "Hiányzó név", "Adj meg projektnevet.")
            return None
        font_family = self.font_combo.currentFont().family()
        return {"id": uuid4().hex, "name": name, "color": qcolor_to_hex8(self._color), "font_family": font_family}

class ProjectsManagerDialog(QDialog):
    def __init__(self, parent=None, projects: Optional[List[dict]] = None):
        super().__init__(parent)
        self.setWindowTitle("Projektek")
        self.setModal(True)
        self.projects: List[dict] = [dict(p) for p in (projects or [])]

        layout = QVBoxLayout(self)
        self.list = QListWidget(); self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        layout.addWidget(self.list)

        btnrow = QHBoxLayout()
        self.add_btn = QPushButton("Új projekt")
        self.edit_btn = QPushButton("Szerkesztés")
        self.del_btn = QPushButton("Törlés")
        btnrow.addWidget(self.add_btn); btnrow.addWidget(self.edit_btn); btnrow.addWidget(self.del_btn); btnrow.addStretch()
        layout.addLayout(btnrow)

        self.add_btn.clicked.connect(self.add_project)
        self.edit_btn.clicked.connect(self.edit_project)
        self.del_btn.clicked.connect(self.delete_project)

        self.refresh_list()

        ok_cancel = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok_cancel.accepted.connect(self.accept); ok_cancel.rejected.connect(self.reject)
        layout.addWidget(ok_cancel)

        self.apply_theme(getattr(parent, "mode", "dark"))

    def apply_theme(self, mode: str):
        if mode == "dark": fg="#FFFFFF"; bg="#121212"; border="#3A3A3A"
        else: fg="#000000"; bg="#FFFFFF"; border="#C8C8C8"
        self.setStyleSheet(f"""
            QDialog, QWidget {{ background-color: {bg}; color: {fg}; }}
            QListWidget {{ background-color: {bg}; color: {fg}; border: 1px solid {border}; }}
            QPushButton {{ color: {fg}; background-color: transparent; border: 1px solid transparent; }}
        """)

    def refresh_list(self):
        self.list.clear()
        for p in self.projects:
            name = p.get("name", "Névtelen")
            color_hex = p.get("color")
            col = hex_to_qcolor(color_hex) or QColor(0, 0, 0, 0)
            item = QListWidgetItem(name)
            item.setIcon(color_swatch_icon(col))
            item.setData(Qt.ItemDataRole.UserRole, p.get("id"))
            self.list.addItem(item)

    def add_project(self):
        dlg = ProjectEditorDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            vals = dlg.get_values()
            if not vals: return
            self.projects.append(vals)
            self.refresh_list()

    def edit_project(self):
        item = self.list.currentItem()
        if not item: return
        pid = item.data(Qt.ItemDataRole.UserRole)
        p = next((x for x in self.projects if x.get("id") == pid), None)
        if not p: return
        dlg = ProjectEditorDialog(self, name=p.get("name",""), color_hex=p.get("color"), font_family=p.get("font_family", UI.font_family))
        if dlg.exec() == QDialog.DialogCode.Accepted:
            vals = dlg.get_values()
            if not vals: return
            vals["id"] = pid
            p.update(vals)
            self.refresh_list()

    def delete_project(self):
        item = self.list.currentItem()
        if not item: return
        pid = item.data(Qt.ItemDataRole.UserRole)
        r = QMessageBox.question(self, "Törlés megerősítése",
                                 "Biztosan törlöd ezt a projektet?",
                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                 QMessageBox.StandardButton.No)
        if r != QMessageBox.StandardButton.Yes: return
        self.projects = [x for x in self.projects if x.get("id") != pid]
        self.refresh_list()

    def get_projects(self) -> List[dict]:
        return [dict(p) for p in self.projects]

# ---------- Számláló dialógus (projekt + „Új projekt…”) ----------
class NewCounterDialog(QDialog):
    def __init__(self, parent=None,
                 default_name: Optional[str] = None,
                 default_dt: Optional[datetime] = None,
                 projects: Optional[List[dict]] = None,
                 default_project_id: Optional[str] = None):
        super().__init__(parent)
        self.setWindowTitle("Számláló")
        self.setModal(True)
        self.projects = projects or []

        layout = QVBoxLayout(self)
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Név:"))
        self.name_edit = QLineEdit(); self.name_edit.setPlaceholderText("Pl.: Választás")
        if default_name: self.name_edit.setText(default_name)
        row1.addWidget(self.name_edit); layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Célidő (Budapest):"))
        self.dt_edit = QDateTimeEdit(); self.dt_edit.setDisplayFormat("yyyy.MM.dd. HH:mm"); self.dt_edit.setCalendarPopup(True)
        if default_dt:
            dt_bud = default_dt.astimezone(TARGET_TZ)
            qdt = QDateTime(dt_bud.year, dt_bud.month, dt_bud.day, dt_bud.hour, dt_bud.minute, dt_bud.second)
            self.dt_edit.setDateTime(qdt)
        else:
            self.dt_edit.setDateTime(QDateTime.currentDateTime().addDays(1))
        row2.addWidget(self.dt_edit); layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Projekt:"))
        self.project_combo = QComboBox(); self._fill_project_combo(self.projects)
        if default_project_id:
            idx = self.project_combo.findData(default_project_id)
            if idx >= 0: self.project_combo.setCurrentIndex(idx)
        row3.addWidget(self.project_combo, 1)
        self.new_proj_btn = QPushButton("Új projekt…"); self.new_proj_btn.setFlat(True); self.new_proj_btn.setCursor(Qt.PointingHandCursor)
        self.new_proj_btn.clicked.connect(self._create_project_inline); row3.addWidget(self.new_proj_btn)
        layout.addLayout(row3)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject); layout.addWidget(btns)

        self.apply_theme(getattr(parent, "mode", "dark"))

    def _fill_project_combo(self, projects: List[dict], select_id: Optional[str] = None):
        self.project_combo.clear()
        self.project_combo.addItem("— Nincs —", "")
        for p in projects:
            self.project_combo.addItem(p.get("name","Névtelen"), p.get("id"))
        if select_id:
            idx = self.project_combo.findData(select_id)
            if idx >= 0:
                self.project_combo.setCurrentIndex(idx)

    def _create_project_inline(self):
        parent_win = self.parent()
        if hasattr(parent_win, "create_project_quick"):
            pid = parent_win.create_project_quick()
            if pid:
                projects = getattr(parent_win, "projects", [])
                self._fill_project_combo(projects, select_id=pid)

    def apply_theme(self, mode: str):
        if mode == "dark": fg="#FFFFFF"; bg="#121212"; input_bg="#1E1E1E"; border="#3A3A3A"
        else: fg="#000000"; bg="#FFFFFF"; input_bg="#FFFFFF"; border="#C8C8C8"
        self.setStyleSheet(f"""
            QDialog, QWidget {{ background-color: {bg}; color: {fg}; }}
            QLineEdit, QDateTimeEdit, QComboBox {{
                background-color: {input_bg}; color: {fg}; border: 1px solid {border};
            }}
            QPushButton {{ color: {fg}; background-color: transparent; border: 1px solid transparent; }}
        """)

    def get_values(self) -> Optional[tuple[str, datetime, Optional[str]]]:
        name = (self.name_edit.text() or "").strip()
        if not name:
            QMessageBox.warning(self, "Hiányzó név", "Adj meg egy nevet a számlálónak.")
            return None
        dt_qt = self.dt_edit.dateTime()
        py_dt_naive = dt_qt.toPython()
        target_dt = py_dt_naive.replace(tzinfo=TARGET_TZ)
        if target_dt <= datetime.now(TARGET_TZ):
            QMessageBox.warning(self, "Rossz időpont", "A célidőnek a jövőben kell lennie.")
            return None
        proj_id = self.project_combo.currentData()
        proj_id = proj_id if proj_id else None
        return name, target_dt, proj_id

# ---------- Számláló sor ----------
class CounterRow(QFrame):
    orderChanged = Signal()
    def __init__(self, cid: str, name: str, target_dt: datetime,
                 on_delete, on_set_bg, on_edit, on_toggle_archive,
                 projects_by_id: Dict[str, dict],
                 project_id: Optional[str] = None,
                 archived: bool = False,
                 bg_hex: Optional[str] = None,
                 parent=None):
        super().__init__(parent)
        self.setObjectName(f"row_{cid}")
        self.cid = cid
        self.name = name
        self.target_dt = target_dt
        self.on_set_bg = on_set_bg
        self.on_edit = on_edit
        self.on_toggle_archive = on_toggle_archive
        self.bg_hex: Optional[str] = bg_hex
        self.project_id: Optional[str] = project_id
        self.archived: bool = bool(archived)
        self.projects_by_id: Dict[str, dict] = projects_by_id
        self.master_opacity: float = 1.0

        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        row = QVBoxLayout(self); row.setContentsMargins(10, 0, 10, 0); row.setSpacing(0)
        top = QHBoxLayout(); top.setContentsMargins(0, 0, 0, 0); top.setSpacing(6)

        self.name_lbl = QLabel(name); self.name_lbl.setStyleSheet("background-color: transparent;")
        top.addWidget(self.name_lbl); top.addStretch()

        self.archive_btn = QPushButton()
        self.archive_btn.setCursor(Qt.PointingHandCursor); self.archive_btn.setFlat(True)
        self.archive_btn.setFixedHeight(UI.button_height)
        self.archive_btn.clicked.connect(self._toggle_archive_clicked)
        top.addWidget(self.archive_btn)

        self.color_btn = QPushButton("Szín")
        self.color_btn.setCursor(Qt.PointingHandCursor); self.color_btn.setFlat(True)
        self.color_btn.setFixedHeight(UI.button_height)
        self.color_btn.clicked.connect(self.pick_color)
        top.addWidget(self.color_btn)

        self.delete_btn = QPushButton("Törlés")
        self.delete_btn.setCursor(Qt.PointingHandCursor); self.delete_btn.setFlat(True)
        self.delete_btn.setFixedHeight(UI.button_height)
        self.delete_btn.clicked.connect(lambda: on_delete(self.cid))
        top.addWidget(self.delete_btn)

        row.addLayout(top)

        self.time_lbl = QLabel("", alignment=Qt.AlignLeft)
        self.time_lbl.setStyleSheet("background-color: transparent;")
        row.addWidget(self.time_lbl)

        self.info_lbl = QLabel("", alignment=Qt.AlignLeft)
        self.info_lbl.setStyleSheet("background-color: transparent;")
        row.addWidget(self.info_lbl)

        self._apply_fonts(UI.font_family)
        self.update_time(datetime.now(TARGET_TZ))
        self._update_color_swatch_icon()
        self.apply_effective_style()
        self._update_archive_btn_text()

    def _toggle_archive_clicked(self):
        new_state = not self.archived
        self.archived = new_state
        self._update_archive_btn_text()
        try:
            self.on_toggle_archive(self.cid, new_state)
        except Exception:
            pass

    def _update_archive_btn_text(self):
        self.archive_btn.setText("Visszaállít" if self.archived else "Archivál")

    def set_master_opacity(self, value: float):
        self.master_opacity = max(0.0, min(1.0, value))
        self.apply_effective_style()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            projects_list = list(self.projects_by_id.values())
            dlg = NewCounterDialog(self,
                                   default_name=self.name,
                                   default_dt=self.target_dt,
                                   projects=projects_list,
                                   default_project_id=self.project_id)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                values = dlg.get_values()
                if values:
                    new_name, new_target, new_proj = values
                    self.name = new_name
                    self.target_dt = new_target
                    self.project_id = new_proj
                    self.name_lbl.setText(new_name)
                    self.update_time(datetime.now(TARGET_TZ))
                    self.apply_effective_style()
                    try:
                        self.on_edit(self.cid, new_name, new_target, new_proj)
                    except Exception:
                        pass
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def set_projects_map(self, projects_by_id: Dict[str, dict]):
        self.projects_by_id = projects_by_id
        self.apply_effective_style()

    def set_project_id(self, pid: Optional[str]):
        self.project_id = pid
        self.apply_effective_style()

    def _apply_fonts(self, family: str):
        self.name_lbl.setFont(QFont(family, UI.font_size_name, QFont.Weight.DemiBold))
        self.time_lbl.setFont(QFont(family, UI.font_size_counter, QFont.Weight.Bold))
        self.info_lbl.setFont(QFont(family, UI.font_size_info))

    def _project_style(self) -> tuple[Optional[str], Optional[str]]:
        if self.project_id and self.project_id in self.projects_by_id:
            p = self.projects_by_id[self.project_id]
            return p.get("color"), p.get("font_family")
        return None, None

    def _with_master_alpha(self, col: QColor) -> QColor:
        a = int(round(col.alpha() * self.master_opacity))
        return QColor(col.red(), col.green(), col.blue(), a)

    def apply_effective_style(self):
        proj_color_hex, proj_font = self._project_style()
        family = proj_font or UI.font_family
        self._apply_fonts(family)

        self.color_btn.setEnabled(proj_color_hex is None)

        if proj_color_hex:
            col = hex_to_qcolor(proj_color_hex)
            if col:
                sc = self._with_master_alpha(col)
                self.setStyleSheet(f"background-color: {qcolor_to_css_rgba(sc)};")
            else:
                self.setStyleSheet("background-color: transparent;")
        else:
            if self.bg_hex:
                col = hex_to_qcolor(self.bg_hex)
                if col:
                    sc = self._with_master_alpha(col)
                    self.setStyleSheet(f"background-color: {qcolor_to_css_rgba(sc)};")
                else:
                    self.setStyleSheet("background-color: transparent;")
            else:
                self.setStyleSheet("background-color: transparent;")

        self._update_color_swatch_icon()

    def pick_color(self):
        if self.project_id:
            QMessageBox.information(self, "Projekt stílus aktív",
                                    "Ez a számláló projekthez tartozik, a projekt színe érvényesül.")
            return
        initial = hex_to_qcolor(self.bg_hex) or QColor(0, 0, 0, 96)
        dlg = QColorDialog(self)
        dlg.setOption(QColorDialog.ColorDialogOption.ShowAlphaChannel, True)
        dlg.setWindowTitle("Háttérszín beállítása")
        dlg.setCurrentColor(initial)
        if dlg.exec():
            col = dlg.selectedColor()
            if not col.isValid(): return
            hex8 = qcolor_to_hex8(col)
            self.bg_hex = hex8
            self.apply_effective_style()
            self._update_color_swatch_icon()
            try:
                self.on_set_bg(self.cid, hex8)
            except Exception:
                pass

    def _update_color_swatch_icon(self):
        col_hex, _ = self._project_style()
        qcol = hex_to_qcolor(col_hex) if col_hex else (hex_to_qcolor(self.bg_hex) or QColor(0,0,0,0))
        ic = color_swatch_icon(qcol, size=14)
        self.color_btn.setIcon(ic)
        self.color_btn.setIconSize(QSize(14, 14))

    def update_time(self, now_bud: datetime):
        delta = self.target_dt - now_bud
        if delta.total_seconds() <= 0:
            self.time_lbl.setText("⏱️ Célidő elérve!")
            self.info_lbl.setText(self.target_dt.strftime("Cél: %Y.%m.%d. %H:%M (Europe/Budapest)"))
            return
        total = int(delta.total_seconds())
        days = total // 86400
        rem = total % 86400
        hours = rem // 3600
        rem %= 3600
        minutes = rem // 60
        seconds = rem % 60
        self.time_lbl.setText(f"{days} nap {hours:02} ó {minutes:02} p {seconds:02} mp")
        self.info_lbl.setText(self.target_dt.strftime("Cél: %Y.%m.%d. %H:%M (Europe/Budapest)"))

    def update_theme(self, fg: str):
        self.name_lbl.setStyleSheet(f"color:{fg}; background-color: transparent;")
        self.time_lbl.setStyleSheet(f"color:{fg}; background-color: transparent;")
        self.info_lbl.setStyleSheet(f"color:{fg}; background-color: transparent;")
        style = make_btn_style(fg)
        self.archive_btn.setStyleSheet(style)
        self.color_btn.setStyleSheet(style)
        self.delete_btn.setStyleSheet(style)

# ---------- Reorderable list ----------
class ReorderableList(QListWidget):
    orderChanged = Signal()
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDragDropOverwriteMode(False)
        self.setSpacing(0)
        self.setStyleSheet("""
            QListWidget { background: transparent; }
            QListWidget::item { background: transparent; }
            QListWidget::item:selected { background: transparent; }
        """)

    def set_drag_enabled(self, enabled: bool):
        self.setDragEnabled(enabled)

    def dropEvent(self, event):
        super().dropEvent(event)
        for i in range(self.count()):
            w = self.itemWidget(self.item(i))
            if w is not None:
                self.item(i).setSizeHint(w.sizeHint())
        self.orderChanged.emit()

# ---------- ICS segéd (egyszerű parser) ----------
def _unfold_ics(text: str) -> List[str]:
    lines = text.splitlines()
    out = []; cur = ""
    for line in lines:
        if line.startswith(" ") or line.startswith("\t"):
            cur += line[1:]
        else:
            if cur: out.append(cur)
            cur = line
    if cur: out.append(cur)
    return out

def _parse_params(header: str) -> Tuple[str, Dict[str, str]]:
    parts = header.split(";")
    key = parts[0].upper()
    params = {}
    for p in parts[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            params[k.upper()] = v
    return key, params

def _parse_ics_dt(val: str, tzid: Optional[str]) -> Tuple[datetime, bool]:
    val = val.strip()
    if len(val) == 8 and val.isdigit():
        dt = datetime.strptime(val, "%Y%m%d")
        return dt.replace(tzinfo=TARGET_TZ), True
    if val.endswith("Z"):
        dt = datetime.strptime(val, "%Y%m%dT%H%M%SZ")
        dt = dt.replace(tzinfo=ZoneInfo("UTC")).astimezone(TARGET_TZ)
        return dt, False
    dt = datetime.strptime(val, "%Y%m%dT%H%M%S")
    if tzid:
        try: tz = ZoneInfo(tzid)
        except Exception: tz = TARGET_TZ
    else:
        tz = TARGET_TZ
    dt = dt.replace(tzinfo=tz).astimezone(TARGET_TZ)
    return dt, False

def parse_ics(text: str) -> List[dict]:
    lines = _unfold_ics(text)
    events = []; in_event = False; cur = {}
    for line in lines:
        if line == "BEGIN:VEVENT":
            in_event = True; cur = {}; continue
        if line == "END:VEVENT":
            if "summary" in cur and "start" in cur:
                events.append(cur)
            in_event = False; cur = {}; continue
        if not in_event: continue
        if ":" not in line: continue
        head, val = line.split(":", 1)
        key, params = _parse_params(head)
        if key == "SUMMARY": cur["summary"] = val
        elif key == "UID": cur["uid"] = val
        elif key == "DTSTART":
            tzid = params.get("TZID"); dt, all_day = _parse_ics_dt(val, tzid)
            cur["start"] = dt; cur["all_day_start"] = all_day
        elif key == "DTEND":
            tzid = params.get("TZID"); dt, all_day = _parse_ics_dt(val, tzid)
            cur["end"] = dt; cur["all_day_end"] = all_day
    return events

class ICSCalendarEditDialog(QDialog):
    def __init__(self, parent=None, name: str = "", url: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Naptár szerkesztése")
        layout = QVBoxLayout(self)

        r1 = QHBoxLayout()
        r1.addWidget(QLabel("Naptár neve:"))
        self.name_edit = QLineEdit(name); r1.addWidget(self.name_edit)
        layout.addLayout(r1)

        r2 = QHBoxLayout()
        r2.addWidget(QLabel("ICS URL:"))
        self.url_edit = QLineEdit(url); self.url_edit.setPlaceholderText("https://.../basic.ics")
        r2.addWidget(self.url_edit)
        layout.addLayout(r2)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        self.apply_theme(getattr(parent, "mode", "dark"))

    def apply_theme(self, mode: str):
        if mode == "dark": fg="#FFFFFF"; bg="#121212"; input_bg="#1E1E1E"; border="#3A3A3A"
        else: fg="#000000"; bg="#FFFFFF"; input_bg="#FFFFFF"; border="#C8C8C8"
        self.setStyleSheet(f"""
            QDialog, QWidget {{ background-color: {bg}; color: {fg}; }}
            QLineEdit {{ background-color: {input_bg}; color: {fg}; border: 1px solid {border}; }}
            QPushButton {{ color: {fg}; background-color: transparent; border: 1px solid transparent; }}
        """)

    def get_values(self) -> Optional[tuple[str, str]]:
        name = (self.name_edit.text() or "").strip()
        url = (self.url_edit.text() or "").strip()
        if not name or not url:
            QMessageBox.warning(self, "Hiányzó adat", "Név és URL megadása kötelező.")
            return None
        return name, url

class ICSEventRow(QWidget):
    def __init__(self, ev: dict, use_end: bool, all_day_time: time, on_start_countdown, parent=None):
        super().__init__(parent)
        self.ev = ev; self.use_end = use_end; self.all_day_time = all_day_time; self.on_start_countdown = on_start_countdown
        lay = QHBoxLayout(self); lay.setContentsMargins(8, 4, 8, 4); lay.setSpacing(8)
        summary = ev.get("summary", "Névtelen")
        start: datetime = ev.get("start")
        end: Optional[datetime] = ev.get("end")
        astart = ev.get("all_day_start", False)
        aend = ev.get("all_day_end", False)
        source = ev.get("source_name")
        sdt = start; edt = end
        if astart: sdt = start.replace(hour=self.all_day_time.hour, minute=self.all_day_time.minute, second=0, microsecond=0)
        if end and aend: edt = end.replace(hour=self.all_day_time.hour, minute=self.all_day_time.minute, second=0, microsecond=0)
        when_str = sdt.strftime("%Y.%m.%d. %H:%M")
        if edt: when_str += "  –  " + edt.strftime("%H:%M")
        src_str = f" <i>({source})</i>" if source else ""
        self.lbl = QLabel(f"<b>{summary}</b> — {when_str}{src_str}")
        self.lbl.setTextFormat(Qt.TextFormat.RichText); lay.addWidget(self.lbl, 1)
        self.btn = QPushButton("⏱ Indít"); self.btn.setCursor(Qt.PointingHandCursor); self.btn.setFlat(True)
        self.btn.clicked.connect(self._start); lay.addWidget(self.btn)

    def _start(self):
        summary = self.ev.get("summary", "Névtelen")
        start: datetime = self.ev.get("start")
        end: Optional[datetime] = self.ev.get("end")
        astart = self.ev.get("all_day_start", False)
        aend = self.ev.get("all_day_end", False)
        target = end if self.use_end and end else start
        if (self.use_end and aend) or ((not self.use_end) and astart):
            target = target.replace(hour=self.all_day_time.hour, minute=self.all_day_time.minute, second=0, microsecond=0)
        self.on_start_countdown(summary, target)

class ICSDialog(QDialog):
    def __init__(self, parent, data_dict: Dict[str, Any], on_start_countdown_cb, mode: str = "dark"):
        super().__init__(parent)
        self.setWindowTitle("Naptár (ICS)"); self.setModal(True)
        self.data = data_dict; self.on_start_countdown_cb = on_start_countdown_cb

        self.data.setdefault("ics", {})
        ics_cfg = self.data["ics"]
        if "url" in ics_cfg and not ics_cfg.get("calendars"):
            ics_cfg["calendars"] = [{"id": uuid4().hex, "name": "Google naptár", "url": ics_cfg["url"], "enabled": True}]
            ics_cfg.pop("url", None)
        ics_cfg.setdefault("calendars", []); ics_cfg.setdefault("use_end_time", False); ics_cfg.setdefault("all_day_time", "09:00")

        self.calendars: List[dict] = ics_cfg["calendars"]
        self.use_end = bool(ics_cfg.get("use_end_time", False))
        all_day_time_str = ics_cfg.get("all_day_time", "09:00")
        try: hh, mm = [int(x) for x in all_day_time_str.split(":")]; self.all_day_time = time(hh, mm)
        except Exception: self.all_day_time = time(9, 0)

        layout = QVBoxLayout(self)
        header = QLabel("<b>Naptárak kezelése</b>"); header.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(header)

        self.cals_list_widget = QListWidget(); self.cals_list_widget.setFrameShape(QFrame.NoFrame)
        layout.addWidget(self.cals_list_widget)

        cal_btn_row = QHBoxLayout()
        self.add_cal_btn = QPushButton("➕ Hozzáadás")
        self.edit_cal_btn = QPushButton("✏️ Szerkesztés")
        self.del_cal_btn = QPushButton("🗑 Törlés")
        cal_btn_row.addWidget(self.add_cal_btn); cal_btn_row.addWidget(self.edit_cal_btn); cal_btn_row.addWidget(self.del_cal_btn); cal_btn_row.addStretch()
        layout.addLayout(cal_btn_row)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Visszaszámláló célja:"))
        self.target_combo = QComboBox(); self.target_combo.addItem("Esemény kezdete", False); self.target_combo.addItem("Esemény vége", True)
        self.target_combo.setCurrentIndex(1 if self.use_end else 0); row2.addWidget(self.target_combo)
        row2.addSpacing(16); row2.addWidget(QLabel("All-day alap idő:"))
        self.all_day_edit = QLineEdit(f"{self.all_day_time.hour:02d}:{self.all_day_time.minute:02d}"); self.all_day_edit.setFixedWidth(60); row2.addWidget(self.all_day_edit)
        self.refresh_btn = QPushButton("🔄 Frissítés"); self.refresh_btn.clicked.connect(self.fetch_and_list)
        row2.addStretch(); row2.addWidget(self.refresh_btn); layout.addLayout(row2)

        self.list = QListWidget(); self.list.setFrameShape(QFrame.NoFrame); layout.addWidget(self.list, 1)
        self.list.itemDoubleClicked.connect(self._on_item_double_clicked)

        btns = QDialogButtonBox(QDialogButtonBox.Close); btns.rejected.connect(self.reject); layout.addWidget(btns)

        self.add_cal_btn.clicked.connect(self.add_calendar)
        self.edit_cal_btn.clicked.connect(self.edit_selected_calendar)
        self.del_cal_btn.clicked.connect(self.delete_selected_calendar)

        self.rebuild_calendar_rows()
        self.apply_theme(mode)

        if any(c.get("enabled", True) for c in self.calendars):
            self.fetch_and_list()

    def apply_theme(self, mode: str):
        if mode == "dark": fg="#FFFFFF"; bg="#121212"; input_bg="#1E1E1E"; border="#3A3A3A"
        else: fg="#000000"; bg="#FFFFFF"; input_bg="#FFFFFF"; border="#C8C8C8"
        self.setStyleSheet(f"""
            QDialog, QWidget {{ background-color: {bg}; color: {fg}; }}
            QListWidget, QListView, QTreeView {{ background-color: {bg}; color: {fg}; border: 1px solid {border}; }}
            QLineEdit, QComboBox {{
                background-color: {input_bg}; color: {fg}; border: 1px solid {border};
                selection-background-color: {fg}; selection-color: {bg};
            }}
            QPushButton {{ color: {fg}; background-color: transparent; border: 1px solid transparent; }}
            QDialogButtonBox QPushButton {{ padding: 6px 12px; }}
        """)

    def rebuild_calendar_rows(self):
        self.cals_list_widget.clear()
        for cal in self.calendars:
            item = QListWidgetItem()
            roww = QWidget(); h = QHBoxLayout(roww); h.setContentsMargins(8, 4, 8, 4); h.setSpacing(10)
            cb = QCheckBox(); cb.setChecked(cal.get("enabled", True))
            cb.toggled.connect(lambda checked, cid=cal["id"]: self.toggle_calendar_enabled(cid, checked))
            h.addWidget(cb)
            name_lbl = QLabel(cal.get("name", "Névtelen naptár")); h.addWidget(name_lbl, 1)
            edit_btn = QPushButton("Szerk."); edit_btn.setFlat(True); edit_btn.clicked.connect(lambda _, cid=cal["id"]: self.edit_calendar(cid))
            del_btn = QPushButton("Töröl"); del_btn.setFlat(True); del_btn.clicked.connect(lambda _, cid=cal["id"]: self.delete_calendar(cid))
            h.addWidget(edit_btn); h.addWidget(del_btn)
            item.setSizeHint(roww.sizeHint()); self.cals_list_widget.addItem(item); self.cals_list_widget.setItemWidget(item, roww)

    def _find_calendar_index(self, cid: str) -> int:
        for i, c in enumerate(self.calendars):
            if c.get("id") == cid:
                return i
        return -1

    def add_calendar(self):
        dlg = ICSCalendarEditDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            vals = dlg.get_values()
            if not vals:
                return
            name, url = vals
            self.calendars.append({
                "id": uuid4().hex,
                "name": name,
                "url": url,
                "enabled": True
            })
            self._save_prefs()
            self.rebuild_calendar_rows()
            self.fetch_and_list()

    def edit_selected_calendar(self):
        row = self.cals_list_widget.currentRow()
        if row < 0 or row >= len(self.calendars):
            return
        cal = self.calendars[row]
        self.edit_calendar(cal["id"])

    def delete_selected_calendar(self):
        row = self.cals_list_widget.currentRow()
        if row < 0 or row >= len(self.calendars):
            return
        cal = self.calendars[row]
        self.delete_calendar(cal["id"])

    def toggle_calendar_enabled(self, cid: str, checked: bool):
        idx = self._find_calendar_index(cid)
        if idx == -1:
            return
        self.calendars[idx]["enabled"] = bool(checked)
        self._save_prefs()
        # nem kell feltétlen fetch, de hasznos:
        self.fetch_and_list()

    def edit_calendar(self, cid: str):
        idx = self._find_calendar_index(cid)
        if idx == -1:
            return
        cal = self.calendars[idx]
        dlg = ICSCalendarEditDialog(self, name=cal.get("name", ""), url=cal.get("url", ""))
        if dlg.exec() == QDialog.DialogCode.Accepted:
            vals = dlg.get_values()
            if not vals:
                return
            name, url = vals
            cal["name"] = name
            cal["url"] = url
            self._save_prefs()
            self.rebuild_calendar_rows()
            self.fetch_and_list()

    def delete_calendar(self, cid: str):
        idx = self._find_calendar_index(cid)
        if idx == -1:
            return
        r = QMessageBox.question(
            self,
            "Törlés megerősítése",
            f"Biztosan törlöd a(z) „{self.calendars[idx].get('name','Névtelen naptár')}” naptárat?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if r != QMessageBox.StandardButton.Yes:
            return
        self.calendars.pop(idx)
        self._save_prefs()
        self.rebuild_calendar_rows()
        self.fetch_and_list()

    def _save_prefs(self):
        self.data.setdefault("ics", {})
        self.data["ics"]["calendars"] = self.calendars
        self.data["ics"]["use_end_time"] = bool(self.target_combo.currentData())
        t = (self.all_day_edit.text().strip() or "09:00"); self.data["ics"]["all_day_time"] = t
        save_data(self.data)

    def _parse_all_day_time(self) -> time:
        t = self.all_day_edit.text().strip() or "09:00"
        try: hh, mm = [int(x) for x in t.split(":")]; return time(hh, mm)
        except Exception: return time(9, 0)

    def fetch_and_list(self):
        self._save_prefs()
        enabled_cals = [c for c in self.calendars if c.get("enabled", True)]
        if not enabled_cals:
            QMessageBox.information(self, "Nincs bekapcsolt naptár", "Kapcsold be legalább egy naptárat.")
            self.list.clear(); return

        events_all: List[dict] = []; errors: List[str] = []
        ctx = ssl.create_default_context()
        for cal in enabled_cals:
            url = cal.get("url", "").strip(); name = cal.get("name", "Névtelen naptár")
            if not url: continue
            try:
                with urllib.request.urlopen(url, timeout=15, context=ctx) as resp:
                    raw = resp.read()
                text = raw.decode("utf-8", errors="replace")
                evs = parse_ics(text)
                for ev in evs: ev["source_name"] = name
                events_all.extend(evs)
            except Exception as e:
                errors.append(f"{name}: {e}")

        now = datetime.now(TARGET_TZ)
        use_end_flag = bool(self.target_combo.currentData())
        all_day_t = self._parse_all_day_time()

        def effective_target(ev: dict) -> datetime:
            start: datetime = ev.get("start"); end: Optional[datetime] = ev.get("end")
            astart = ev.get("all_day_start", False); aend = ev.get("all_day_end", False)
            t = end if (use_end_flag and end) else start
            if (use_end_flag and aend) or ((not use_end_flag) and astart):
                t = t.replace(hour=all_day_t.hour, minute=all_day_t.minute, second=0, microsecond=0)
            return t

        events_sorted = sorted(events_all, key=lambda ev: effective_target(ev))
        events_sorted = [ev for ev in events_sorted if effective_target(ev) >= now.replace(second=0, microsecond=0)]

        self.list.clear()
        for ev in events_sorted:
            roww = ICSEventRow(ev, use_end_flag, all_day_t, self._start_countdown_from_event)
            item = QListWidgetItem(); item.setSizeHint(roww.sizeHint())
            item.setData(Qt.ItemDataRole.UserRole, ev)
            self.list.addItem(item); self.list.setItemWidget(item, roww)

        if errors:
            QMessageBox.warning(self, "Néhány naptár nem tölthető be", "\n".join(errors))

    def _start_countdown_from_event(self, name: str, target: datetime):
        self.on_start_countdown_cb(name, target)
        QMessageBox.information(self, "Hozzáadva", f"Visszaszámláló indítva:\n{name}\n→ {target.strftime('%Y.%m.%d. %H:%M')}")

    def _on_item_double_clicked(self, item: QListWidgetItem):
        ev = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(ev, dict): return
        summary = ev.get("summary", "Névtelen")
        start: datetime = ev.get("start"); end: Optional[datetime] = ev.get("end")
        astart = ev.get("all_day_start", False); aend = ev.get("all_day_end", False)
        use_end_flag = bool(self.target_combo.currentData())
        all_day_t = self._parse_all_day_time()
        target = end if (use_end_flag and end) else start
        if (use_end_flag and aend) or ((not use_end_flag) and astart):
            target = target.replace(hour=all_day_t.hour, minute=all_day_t.minute, second=0, microsecond=0)

        parent_win = self.parent()
        default_project_id = getattr(parent_win, "current_filter_project_id", None)
        projects = self.data.get("projects", [])

        dlg = NewCounterDialog(parent=parent_win, default_name=summary, default_dt=target, projects=projects, default_project_id=default_project_id)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            values = dlg.get_values()
            if not values: return
            name, dt, proj_id = values
            try:
                parent_win.add_counter(name, dt, proj_id)
            except Exception:
                self.on_start_countdown_cb(name, dt)
            QMessageBox.information(self, "Hozzáadva", f"Visszaszámláló létrehozva:\n{name}\n→ {dt.strftime('%Y.%m.%d. %H:%M')}")

# ---------- Stílus beállítások ----------
class StyleDialog(QDialog):
    def __init__(self, parent, current_opacity: float, mode: str, current_style: dict):
        super().__init__(parent)
        self.setWindowTitle("Stílus beállítások")
        self.setModal(True)

        # Kiinduló értékek
        self._opacity = int(round(current_opacity * 100))
        ff = current_style.get("font_family", UI.font_family)
        fs = current_style.get("font_sizes", {})
        sz_title   = int(fs.get("title", UI.font_size_title))
        sz_name    = int(fs.get("name", UI.font_size_name))
        sz_counter = int(fs.get("counter", UI.font_size_counter))
        sz_info    = int(fs.get("info", UI.font_size_info))
        sz_button  = int(fs.get("button", UI.font_size_button))

        layout = QVBoxLayout(self)

        # Átlátszóság
        r_op = QHBoxLayout()
        self.opacity_label = QLabel(f"Átlátszóság: {self._opacity}%")
        r_op.addWidget(self.opacity_label); r_op.addStretch()
        layout.addLayout(r_op)

        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setMinimum(10); self.opacity_slider.setMaximum(100)
        self.opacity_slider.setSingleStep(1); self.opacity_slider.setPageStep(5)
        self.opacity_slider.setValue(self._opacity)
        self.opacity_slider.valueChanged.connect(lambda v: self.opacity_label.setText(f"Átlátszóság: {v}%"))
        layout.addWidget(self.opacity_slider)

        # Betűtípus
        r_ff = QHBoxLayout()
        r_ff.addWidget(QLabel("Default betűtípus:"))
        self.font_combo = QFontComboBox(); self.font_combo.setCurrentFont(QFont(ff))
        r_ff.addWidget(self.font_combo)
        layout.addLayout(r_ff)

        # Betűméretek
        def row_spin(label: str, val: int, minv: int = 8, maxv: int = 72) -> QSpinBox:
            rr = QHBoxLayout()
            rr.addWidget(QLabel(label))
            sp = QSpinBox(); sp.setRange(minv, maxv); sp.setValue(val)
            # --- JAV: dedikált plusz/mínusz gombok, hogy a "-" gomb biztosan kattintható legyen ---
            sp.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.PlusMinus)
            rr.addWidget(sp); rr.addStretch()
            layout.addLayout(rr)
            return sp

        self.sz_title_sp   = row_spin("Cím méret (px):", sz_title, 10, 96)
        self.sz_name_sp    = row_spin("Név méret (px):", sz_name, 8, 72)
        self.sz_counter_sp = row_spin("Számláló méret (px):", sz_counter, 12, 120)
        self.sz_info_sp    = row_spin("Info méret (px):", sz_info, 8, 48)
        self.sz_button_sp  = row_spin("Gomb méret (px):", sz_button, 8, 48)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        self.apply_theme(mode)

    def apply_theme(self, mode: str):
        if mode == "dark": fg="#FFFFFF"; bg="#121212"; input_bg="#1E1E1E"; border="#3A3A3A"
        else: fg="#000000"; bg="#FFFFFF"; input_bg="#FFFFFF"; border="#C8C8C8"
        # --- JAV: Spinbox gombszélességek rögzítése, hogy a mínusz/plusz gombok biztosan külön klikkelhetőek legyenek ---
        self.setStyleSheet(f"""
            QDialog, QWidget {{ background-color: {bg}; color: {fg}; }}
            QLineEdit, QSpinBox, QComboBox {{
                background-color: {input_bg}; color: {fg}; border: 1px solid {border};
            }}
            QFontComboBox {{ background-color: {input_bg}; color: {fg}; border: 1px solid {border}; }}
            QSlider::groove:horizontal {{ height: 6px; background: {border}; }}
            QSlider::handle:horizontal {{ width: 14px; height: 14px; background: {fg}; margin: -5px 0; }}
            QPushButton {{ color: {fg}; background-color: transparent; border: 1px solid transparent; }}

            /* Spinbox gombok — külön szélesség, hogy ne „olvadjanak” a szövegmezőbe */
            QSpinBox::up-button   {{ width: 22px; }}
            QSpinBox::down-button {{ width: 22px; }}
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
                background: rgba(127,127,127,0.15);
            }}
        """)

    def get_values(self) -> dict:
        return {
            "opacity": self.opacity_slider.value() / 100.0,
            "font_family": self.font_combo.currentFont().family(),
            "font_sizes": {
                "title":   self.sz_title_sp.value(),
                "name":    self.sz_name_sp.value(),
                "counter": self.sz_counter_sp.value(),
                "info":    self.sz_info_sp.value(),
                "button":  self.sz_button_sp.value(),
            }
        }

# ---------- Sorrend opciók ----------
SORT_OPTIONS = [
    ("manual", "Manuális sorrend"),
    ("project", "Projekt szerint"),
    ("due_asc", "Lejárat szerint növekvő"),
    ("due_desc", "Lejárat szerint csökkenő"),
]

# ---------- Fő ablak ----------
class CountdownWindow(QWidget):
    RESIZE_MARGIN = 6  # keret nélküli ablak szélein fogás

    def __init__(self):
        super().__init__()

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowTitle("Visszaszámlálók")

        self.data = load_data()
        self.mode = self.data.get("mode", "dark")
        self.master_opacity: float = float(self.data.get("opacity", UI.bg_opacity))
        self.bg_alpha = int(round(255 * self.master_opacity))

        self._saved_pos = self.data.get("window_pos")
        self._position_restored = False

        self.projects: List[dict] = self.data.get("projects", [])
        self.projects_by_id: Dict[str, dict] = {p["id"]: p for p in self.projects if "id" in p}

        self.current_filter_project_id: Optional[str] = None
        self.show_archived: bool = bool(self.data.get("show_archived", False))
        self.sort_mode: str = self.data.get("sort_mode", "manual")

        # Gyökér splitter: bal sáv | fő terület
        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        root_layout = QHBoxLayout(self); root_layout.setContentsMargins(20, 16, 20, 20); root_layout.addWidget(self.splitter)

        # ---- Bal oldali sáv widget ----
        self.sidebar = QWidget()
        side = QVBoxLayout(self.sidebar); side.setContentsMargins(0,0,0,0); side.setSpacing(8)

        self.add_btn = QPushButton("➕ Új számláló"); self._prep_btn(self.add_btn, self.add_counter_dialog)
        side.addWidget(self.add_btn)

        self.style_btn = QPushButton("🎨 Stílus"); self._prep_btn(self.style_btn, self.open_style_dialog)
        side.addWidget(self.style_btn)

        self.calendar_btn = QPushButton("📅 Naptárak"); self._prep_btn(self.calendar_btn, self.open_calendar_dialog)
        side.addWidget(self.calendar_btn)

        self.manage_projects_btn = QPushButton("📁 Projektek"); self._prep_btn(self.manage_projects_btn, self.manage_projects_dialog)
        side.addWidget(self.manage_projects_btn)

        side.addStretch()

        # ---- Jobb oldali fő terület ----
        self.main_area = QWidget()
        self.main_layout = QVBoxLayout(self.main_area); self.main_layout.setContentsMargins(0,0,0,0); self.main_layout.setSpacing(12)

        # Felső sáv
        self.topbar_widget = QWidget()
        top = QHBoxLayout(self.topbar_widget); top.setContentsMargins(0,0,0,0); top.setSpacing(8)

        self.title_lbl = QLabel("Visszaszámlálók"); self.title_lbl.setStyleSheet("background-color: transparent;")
        self.title_lbl.setFont(QFont(UI.font_family, UI.font_size_title, QFont.Weight.DemiBold))
        top.addWidget(self.title_lbl)

        # Projekt szűrő
        top.addSpacing(12)
        self.filter_lbl = QLabel("Projekt szűrő:")
        self.filter_combo = QComboBox(); self._populate_filter_combo()
        self.filter_combo.currentIndexChanged.connect(self.on_filter_changed)
        top.addWidget(self.filter_lbl); top.addWidget(self.filter_combo)

        # Rendezés
        top.addSpacing(12)
        self.sort_lbl = QLabel("Sorrend:")
        self.sort_combo = QComboBox()
        for key, text in SORT_OPTIONS: self.sort_combo.addItem(text, key)
        idx = self.sort_combo.findData(self.sort_mode)
        if idx >= 0: self.sort_combo.setCurrentIndex(idx)
        self.sort_combo.currentIndexChanged.connect(self.on_sort_changed)
        top.addWidget(self.sort_lbl); top.addWidget(self.sort_combo)

        self.sort_btn = QPushButton("Rendezés ▾"); self.sort_btn.setFlat(True); self.sort_btn.setCursor(Qt.PointingHandCursor)
        self.sort_menu = QMenu(self); self._build_sort_menu(); self.sort_btn.setMenu(self.sort_menu)
        top.addWidget(self.sort_btn)

        # Archiváltak
        self.show_archived_btn = QPushButton(); self._prep_btn(self.show_archived_btn, self.toggle_show_archived, flat=True)
        top.addWidget(self.show_archived_btn)

        # Téma + bezárás
        self.toggle_btn = QPushButton("☀️ Világos mód"); self._prep_btn(self.toggle_btn, self.toggle_mode, flat=True)
        top.addWidget(self.toggle_btn)

        self.close_btn = QPushButton("✖"); self._prep_btn(self.close_btn, self.close, flat=True)
        top.addWidget(self.close_btn)

        top.addStretch()
        self.main_layout.addWidget(self.topbar_widget)

        # Lista
        self.list = ReorderableList(); self.list.setFrameShape(QFrame.NoFrame)
        self.list.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
        self.list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.orderChanged.connect(self.persist_order)
        self.main_layout.addWidget(self.list, 1)

        # Splitter összeállítása
        self.splitter.addWidget(self.sidebar)
        self.splitter.addWidget(self.main_area)
        self.splitter.setCollapsible(0, False); self.splitter.setCollapsible(1, False)
        if isinstance(self.data.get("splitter_sizes"), list):
            try:
                self.splitter.setSizes([int(self.data["splitter_sizes"][0]), int(self.data["splitter_sizes"][1])])
            except Exception:
                self.splitter.setSizes([220, 680])
        else:
            self.splitter.setSizes([220, 680])

        # Gyűjtők
        self.rows: Dict[str, CounterRow] = {}; self.items: Dict[str, QListWidgetItem] = {}
        self.rebuild_list()

        # Másodperchez igazított frissítés
        self.second_timer = QTimer(self); self.second_timer.setSingleShot(True); self.second_timer.timeout.connect(self._on_second)
        self.update_times(); self._arm_next_tick()

        self.resize(UI.window_width, UI.window_height)
        self.update_theme()
        self._drag_offset: Optional[QPoint] = None
        self._resizing = False; self._resize_edge = None

        self._adapt_sort_controls()

    # ----- Segéd a gombokhoz -----
    def _prep_btn(self, btn: QPushButton, slot, flat: bool=True):
        btn.setCursor(Qt.PointingHandCursor); btn.setFlat(flat); btn.setFixedHeight(UI.button_height); btn.clicked.connect(slot)

    # ----- Stílus ablak -----
    def open_style_dialog(self):
        current_style = _build_style_dict_from_UI()
        dlg = StyleDialog(self, current_opacity=self.master_opacity, mode=self.mode, current_style=current_style)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            vals = dlg.get_values()
            # Mentés UI <- vals
            UI.font_family = vals["font_family"]
            UI.font_size_title   = vals["font_sizes"]["title"]
            UI.font_size_name    = vals["font_sizes"]["name"]
            UI.font_size_counter = vals["font_sizes"]["counter"]
            UI.font_size_info    = vals["font_sizes"]["info"]
            UI.font_size_button  = vals["font_sizes"]["button"]
            self.set_master_opacity(vals["opacity"])

            # Persist style
            self.data["style"] = _build_style_dict_from_UI()
            save_data(self.data)

            # Alkalmazás a teljes UI-ra
            self.apply_global_fonts_and_styles()

    def apply_global_fonts_and_styles(self):
        # App-level default betűtípus
        QApplication.instance().setFont(QFont(UI.font_family))

        # Topbar felirat
        self.title_lbl.setFont(QFont(UI.font_family, UI.font_size_title, QFont.Weight.DemiBold))

        # Gomb stílus frissítés (méret!)
        self.update_theme()

        # Sorok frissítése
        for i in range(self.list.count()):
            row = self.list.itemWidget(self.list.item(i))
            if isinstance(row, CounterRow):
                row.apply_effective_style()

        # Lista magasság stb.
        QTimer.singleShot(0, self.adjust_height_to_content)

    # ----- Rendezés menü -----
    def _build_sort_menu(self):
        self.sort_menu.clear()
        for key, text in SORT_OPTIONS:
            act = QAction(text, self)
            act.setCheckable(True)
            act.setChecked(key == self.sort_mode)
            act.triggered.connect(lambda _, k=key: self._set_sort_mode_from_menu(k))
            self.sort_menu.addAction(act)

    def _set_sort_mode_from_menu(self, key: str):
        self.sort_mode = key
        self.data["sort_mode"] = self.sort_mode
        save_data(self.data)
        idx = self.sort_combo.findData(self.sort_mode)
        if idx >= 0:
            self.sort_combo.blockSignals(True)
            self.sort_combo.setCurrentIndex(idx)
            self.sort_combo.blockSignals(False)
        self._build_sort_menu()
        self._apply_drag_enabled()
        self.rebuild_list()
        self.update_theme()

    # ----- Másodperchez igazított tick -----
    def _arm_next_tick(self):
        now = QDateTime.currentDateTime()
        ms_to_next = 1000 - now.time().msec()
        if ms_to_next < 10: ms_to_next += 1000
        self.second_timer.start(ms_to_next)

    def _on_second(self):
        self.update_times(); self._arm_next_tick()

    # ----- Rajzolás -----
    def paintEvent(self, event):
        painter = QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing, True); painter.setPen(Qt.PenStyle.NoPen)
        bg = QColor(0, 0, 0, self.bg_alpha) if self.mode == "dark" else QColor(255, 255, 255, self.bg_alpha)
        painter.setBrush(bg); rect = self.rect().adjusted(0, 0, -1, -1); painter.drawRect(rect)

    # ----- Életciklus -----
    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.adjust_height_to_content)

    def adjust_height_to_content(self):
        # a fő területhez igazítunk; a teljes ablakmagasságot limitálja az availableGeometry
        margins = self.main_layout.contentsMargins()
        spacing = self.main_layout.spacing()
        top_h = self.topbar_widget.sizeHint().height()
        count = self.list.count()
        list_h = sum(self.list.sizeHintForRow(i) for i in range(count))
        if count > 0:
            list_h += self.list.spacing() * (count - 1)
        desired_h = margins.top() + margins.bottom() + top_h + spacing + list_h
        desired_h = max(desired_h, UI.window_height)

        screen = (self.windowHandle().screen() if self.windowHandle() else None) \
                 or QGuiApplication.screenAt(QCursor.pos()) \
                 or QGuiApplication.primaryScreen()
        if not screen: return
        avail = screen.availableGeometry()
        cap_h = avail.height()

        final_h = min(desired_h, cap_h)

        if desired_h > cap_h:
            self.list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        else:
            self.list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.resize(self.width(), int(final_h))
        self._restore_initial_position()

    def _restore_initial_position(self):
        if self._position_restored: return
        self._position_restored = True
        if isinstance(self.data.get("splitter_sizes"), list):
            try:
                self.splitter.setSizes([int(self.data["splitter_sizes"][0]), int(self.data["splitter_sizes"][1])])
            except Exception:
                pass
        if isinstance(self._saved_pos, list) and len(self._saved_pos) == 2:
            x, y = int(self._saved_pos[0]), int(self._saved_pos[1])
            sx, sy = self._clamp_to_some_screen(x, y); self.move(sx, sy)
        else:
            self.move_to_top_right_exact()

    def _clamp_to_some_screen(self, x: int, y: int) -> tuple[int, int]:
        point = QPoint(x, y); screen = QGuiApplication.screenAt(point) or QGuiApplication.primaryScreen()
        geo = screen.geometry()
        min_x = geo.x(); max_x = geo.x() + geo.width() - self.width()
        min_y = geo.y(); max_y = geo.y() + geo.height() - self.height()
        return max(min_x, min(x, max_x)), max(min_y, min(y, max_y))

    def move_to_top_right_exact(self):
        screen = (self.windowHandle().screen() if self.windowHandle() else None) \
                 or QGuiApplication.screenAt(QCursor.pos()) \
                 or QGuiApplication.primaryScreen()
        if not screen: return
        geo = screen.geometry()
        x = geo.x() + geo.width() - self.width()
        y = geo.y()
        self.move(x, y)

    # ----- Egér: mozgatás + keret nélküli átméretezés -----
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            edge = self._hit_test_resize_edge(e.position().toPoint())
            if edge:
                self._resizing = True
                self._resize_edge = edge
                self._start_geo = self.geometry()
                self._start_pos = e.globalPosition().toPoint()
            else:
                self._drag_offset = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            e.accept()

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        if self._resizing and self._resize_edge:
            self._do_resize(e.globalPosition().toPoint())
            e.accept()
            return
        # kurzor változtatása
        edge = self._hit_test_resize_edge(pos)
        if edge in ("left","right"):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif edge in ("top","bottom"):
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        elif edge in ("topleft","bottomright"):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif edge in ("topright","bottomleft"):
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

        if e.buttons() & Qt.MouseButton.LeftButton and self._drag_offset is not None:
            self.move(e.globalPosition().toPoint() - self._drag_offset)
            e.accept()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            if self._resizing:
                self._resizing = False; self._resize_edge = None
            self._drag_offset = None
            e.accept()

    def _hit_test_resize_edge(self, p: QPoint) -> Optional[str]:
        r = self.rect()
        m = self.RESIZE_MARGIN
        left   = abs(p.x() - r.left())   <= m
        right  = abs(p.x() - r.right())  <= m
        top    = abs(p.y() - r.top())    <= m
        bottom = abs(p.y() - r.bottom()) <= m
        if top and left: return "topleft"
        if top and right: return "topright"
        if bottom and left: return "bottomleft"
        if bottom and right: return "bottomright"
        if left: return "left"
        if right: return "right"
        if top: return "top"
        if bottom: return "bottom"
        return None

    def _do_resize(self, global_pos: QPoint):
        dx = global_pos.x() - self._start_pos.x()
        dy = global_pos.y() - self._start_pos.y()
        g: QRect = QRect(self._start_geo)
        edge = self._resize_edge
        if edge in ("right","topright","bottomright"):
            g.setWidth(max(400, self._start_geo.width() + dx))
        if edge in ("left","topleft","bottomleft"):
            new_w = max(400, self._start_geo.width() - dx)
            g.setLeft(self._start_geo.right() - new_w)
        if edge in ("bottom","bottomleft","bottomright"):
            g.setHeight(max(300, self._start_geo.height() + dy))
        if edge in ("top","topleft","topright"):
            new_h = max(300, self._start_geo.height() - dy)
            g.setTop(self._start_geo.bottom() - new_h)
        self.setGeometry(g)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.close()

    def closeEvent(self, event):
        try:
            top_left = self.frameGeometry().topLeft()
            self.data["window_pos"] = [int(top_left.x()), int(top_left.y())]
            self.data["mode"] = self.mode
            self.data["opacity"] = self.master_opacity
            self.data["show_archived"] = self.show_archived
            self.data["sort_mode"] = self.sort_mode
            self.data["splitter_sizes"] = self.splitter.sizes()
            self.data["style"] = _build_style_dict_from_UI()
            save_data(self.data)
        except Exception:
            pass
        super().closeEvent(event)

    # ---- ADAPTÍV rendezés vezérlő ----
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._adapt_sort_controls()

    def _adapt_sort_controls(self):
        area_w = self.main_area.width()
        narrow = area_w < 720
        self.sort_lbl.setVisible(not narrow)
        self.sort_combo.setVisible(not narrow)
        self.sort_btn.setVisible(narrow)

    # ---- SORREND LOGIKA ----
    def on_sort_changed(self, idx: int):
        self.sort_mode = self.sort_combo.currentData() or "manual"
        self.data["sort_mode"] = self.sort_mode; save_data(self.data)
        self._build_sort_menu()
        self._apply_drag_enabled()
        self.rebuild_list()
        self.update_theme()

    def _apply_drag_enabled(self):
        self.list.set_drag_enabled(self.sort_mode == "manual")

    def _sorted_entries(self, entries: List[dict]) -> List[dict]:
        if self.sort_mode == "manual":
            return entries
        def tgt(entry):
            dt = datetime.fromisoformat(entry["target"])
            if dt.tzinfo is None: dt = dt.replace(tzinfo=TARGET_TZ)
            return dt
        if self.sort_mode == "project":
            def proj_name(entry):
                pid = entry.get("project_id")
                if pid and pid in self.projects_by_id:
                    return self.projects_by_id[pid].get("name", "").lower()
                return "\uFFFF"
            return sorted(entries, key=lambda e: (proj_name(e), tgt(e)))
        if self.sort_mode == "due_asc":
            return sorted(entries, key=lambda e: tgt(e))
        if self.sort_mode == "due_desc":
            return sorted(entries, key=lambda e: tgt(e), reverse=True)
        return entries

    # lista építés (szűrő + archív + sorrend)
    def rebuild_list(self):
        self.list.clear(); self.rows.clear(); self.items.clear()
        raw = self.data.get("counters", [])
        entries = [c for c in raw if self._passes_filter(c)]
        entries = self._sorted_entries(entries)

        for c in entries:
            cid = c["id"]; name = c["name"]
            target = datetime.fromisoformat(c["target"])
            if target.tzinfo is None: target = target.replace(tzinfo=TARGET_TZ)
            bg_hex = c.get("bg"); proj_id = c.get("project_id"); archived = bool(c.get("archived", False))

            row = CounterRow(
                cid, name, target,
                self.delete_counter, self.set_counter_bg, self.edit_counter, self.set_archived,
                projects_by_id=self.projects_by_id,
                project_id=proj_id,
                archived=archived,
                bg_hex=bg_hex
            )
            row.set_master_opacity(self.master_opacity)

            item = QListWidgetItem()
            flags = item.flags() | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDragEnabled
            item.setFlags(flags); item.setSizeHint(row.sizeHint())
            self.list.addItem(item); self.list.setItemWidget(item, row)
            self.rows[cid] = row; self.items[cid] = item

        self._apply_drag_enabled()
        QTimer.singleShot(0, self.adjust_height_to_content)

    # szűrő
    def _populate_filter_combo(self, keep_selection: bool = False):
        prev_id = self.current_filter_project_id if keep_selection else None
        self.filter_combo.blockSignals(True); self.filter_combo.clear()
        self.filter_combo.addItem("Összes", "")
        for p in self.projects:
            self.filter_combo.addItem(p.get("name", "Névtelen"), p.get("id"))
        index = 0
        if prev_id:
            idx = self.filter_combo.findData(prev_id)
            if idx >= 0: index = idx
        self.filter_combo.setCurrentIndex(index)
        self.current_filter_project_id = self.filter_combo.currentData() or None
        self.filter_combo.blockSignals(False)

    def _passes_filter(self, counter_entry: dict) -> bool:
        if self.current_filter_project_id and counter_entry.get("project_id") != self.current_filter_project_id:
            return False
        archived = bool(counter_entry.get("archived", False))
        if archived and not self.show_archived:
            return False
        return True

    def on_filter_changed(self, idx: int):
        self.current_filter_project_id = self.filter_combo.currentData() or None
        self.rebuild_list(); self.update_theme()
        QTimer.singleShot(0, self.adjust_height_to_content)

    # archív megjelenítés kapcsoló
    def toggle_show_archived(self):
        self.show_archived = not self.show_archived
        self.data["show_archived"] = self.show_archived; save_data(self.data)
        self.rebuild_list(); self.update_theme()
        QTimer.singleShot(0, self.adjust_height_to_content)

    # idő frissítés
    def update_times(self):
        now_bud = datetime.now(TARGET_TZ)
        for i in range(self.list.count()):
            row = self.list.itemWidget(self.list.item(i))
            if isinstance(row, CounterRow): row.update_time(now_bud)

    # sorrend mentése (csak manuális módban!)
    def persist_order(self):
        if self.sort_mode != "manual":
            return
        visible_order: list[str] = []
        for i in range(self.list.count()):
            row = self.list.itemWidget(self.list.item(i))
            if isinstance(row, CounterRow): visible_order.append(row.cid)
        visible_set = set(visible_order)
        old_list = self.data.get("counters", [])
        id_to_entry = {c["id"]: c for c in old_list}
        it = iter(visible_order); new_list = []
        for c in old_list:
            cid = c["id"]
            if cid in visible_set:
                next_id = next(it); new_list.append(id_to_entry[next_id])
            else:
                new_list.append(c)
        self.data["counters"] = new_list; save_data(self.data)
        QTimer.singleShot(0, self.adjust_height_to_content)

    # per-számláló háttérszín mentése
    def set_counter_bg(self, cid: str, bg_hex: Optional[str]):
        changed = False
        for c in self.data.get("counters", []):
            if c.get("id") == cid:
                if bg_hex: c["bg"] = bg_hex
                else: c.pop("bg", None)
                changed = True; break
        if changed: save_data(self.data)

    # archív állapot mentése
    def set_archived(self, cid: str, archived: bool):
        for c in self.data.get("counters", []):
            if c.get("id") == cid:
                c["archived"] = bool(archived); break
        save_data(self.data)
        if not self.show_archived and archived:
            self.rebuild_list()
        else:
            self.update_theme()

    # szerkesztés mentése
    def edit_counter(self, cid: str, new_name: str, new_target_dt: datetime, new_project_id: Optional[str]):
        for c in self.data.get("counters", []):
            if c.get("id") == cid:
                c["name"] = new_name; c["target"] = new_target_dt.isoformat()
                if new_project_id: c["project_id"] = new_project_id
                else: c.pop("project_id", None)
                break
        save_data(self.data)
        self.rebuild_list(); self.update_times()

    # projektek menedzsment
    def manage_projects_dialog(self):
        dlg = ProjectsManagerDialog(self, self.projects)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_projects = dlg.get_projects()
            valid_ids = {p["id"] for p in new_projects if "id" in p}
            for c in self.data.get("counters", []):
                pid = c.get("project_id")
                if pid and pid not in valid_ids:
                    c.pop("project_id", None)
            self.projects = new_projects; self.data["projects"] = self.projects; save_data(self.data)
            self.projects_by_id = {p["id"]: p for p in self.projects if "id" in p}
            self._populate_filter_combo(keep_selection=True); self.rebuild_list()
            for i in range(self.list.count()):
                row = self.list.itemWidget(self.list.item(i))
                if isinstance(row, CounterRow):
                    row.set_projects_map(self.projects_by_id); row.set_master_opacity(self.master_opacity)
            QTimer.singleShot(0, self.adjust_height_to_content)

    # gyors új projekt a számláló dialógusból
    def create_project_quick(self) -> Optional[str]:
        dlg = ProjectEditorDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            vals = dlg.get_values()
            if not vals: return None
            self.projects.append(vals); self.data["projects"] = self.projects; save_data(self.data)
            self.projects_by_id = {p["id"]: p for p in self.projects if "id" in p}
            self._populate_filter_combo(keep_selection=True)
            return vals["id"]
        return None

    # műveletek
    def add_counter_dialog(self):
        dlg = NewCounterDialog(self, projects=self.projects, default_project_id=self.current_filter_project_id)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            values = dlg.get_values()
            if not values: return
            name, target_dt, proj_id = values
            self.add_counter(name, target_dt, proj_id)

    def add_counter(self, name: str, target_dt: datetime, project_id: Optional[str]):
        cid = uuid4().hex
        entry = {"id": cid, "name": name, "target": target_dt.isoformat(), "archived": False}
        if project_id: entry["project_id"] = project_id
        self.data.setdefault("counters", []).append(entry); save_data(self.data)

        if self.sort_mode != "manual" or not self._passes_filter(entry):
            self.rebuild_list()
        else:
            row = CounterRow(
                cid, name, target_dt,
                self.delete_counter, self.set_counter_bg, self.edit_counter, self.set_archived,
                projects_by_id=self.projects_by_id,
                project_id=project_id,
                archived=False,
                bg_hex=None
            )
            row.set_master_opacity(self.master_opacity)
            item = QListWidgetItem()
            flags = item.flags() | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDragEnabled
            item.setFlags(flags); item.setSizeHint(row.sizeHint())
            self.list.addItem(item); self.list.setItemWidget(item, row)
            self.rows[cid] = row; self.items[cid] = item

        self.update_theme(); self.update_times()
        QTimer.singleShot(0, self.adjust_height_to_content)

    def delete_counter(self, cid: str):
        r = QMessageBox.question(self, "Törlés megerősítése",
                                 "Biztosan törlöd ezt a számlálót?",
                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                 QMessageBox.StandardButton.No)
        if r != QMessageBox.StandardButton.Yes: return
        self.data["counters"] = [c for c in self.data.get("counters", []) if c["id"] != cid]; save_data(self.data)
        self.rebuild_list()
        self.update()
        QTimer.singleShot(0, self.adjust_height_to_content)

    # téma
    def toggle_mode(self):
        self.mode = "light" if self.mode == "dark" else "dark"
        self.data["mode"] = self.mode; save_data(self.data)
        self.update_theme(); self.update()

    def set_master_opacity(self, value: float):
        self.master_opacity = max(0.10, min(1.0, value))
        self.data["opacity"] = self.master_opacity; save_data(self.data)
        self.bg_alpha = int(round(255 * self.master_opacity)); self.update()
        for i in range(self.list.count()):
            row = self.list.itemWidget(self.list.item(i))
            if isinstance(row, CounterRow): row.set_master_opacity(self.master_opacity)

    def _update_show_archived_btn_text(self):
        self.show_archived_btn.setText("📦 Archiváltak megjelenítése" if not self.show_archived else "📦 Archiváltak elrejtése")
        self.show_archived_btn.setToolTip("Archív visszaszámlálók mutatása/elrejtése")

    def update_theme(self):
        self.toggle_btn.setText("☀️ Világos mód" if self.mode == "dark" else "🌙 Sötét mód")
        self.toggle_btn.setToolTip("Váltás világos módra" if self.mode == "dark" else "Váltás sötét módra")
        self._update_show_archived_btn_text()

        fg = "white" if self.mode == "dark" else "black"
        style = make_btn_style(fg)
        for b in (self.add_btn, self.style_btn, self.calendar_btn, self.manage_projects_btn,
                  self.toggle_btn, self.close_btn, self.show_archived_btn, self.sort_btn):
            b.setStyleSheet(style)
        # cím és címkék betű
        self.title_lbl.setFont(QFont(UI.font_family, UI.font_size_title, QFont.Weight.DemiBold))
        self.title_lbl.setStyleSheet(f"color:{fg}; background-color: transparent;")
        self.filter_lbl.setStyleSheet(f"color:{fg}; background-color: transparent;")
        self.sort_lbl.setStyleSheet(f"color:{fg}; background-color: transparent;")
        # Combók
        self.filter_combo.setStyleSheet(f"color:{fg}; background-color: transparent;")
        self.sort_combo.setStyleSheet(f"color:{fg}; background-color: transparent;")

        self.sort_menu.setStyleSheet(f"""
            QMenu {{ background-color: transparent; color: {fg}; }}
            QMenu::item:selected {{ background: rgba(127,127,127,64); }}
        """)

        # Sorok frissítése
        for i in range(self.list.count()):
            row = self.list.itemWidget(self.list.item(i))
            if isinstance(row, CounterRow):
                row.update_theme(fg)

    # naptár
    def open_calendar_dialog(self):
        dlg = ICSDialog(self, self.data, self._start_countdown_from_calendar, mode=self.mode)
        dlg.exec()

    def _start_countdown_from_calendar(self, name: str, target: datetime):
        self.add_counter(name, target, self.current_filter_project_id)

if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    # Globális default betűtípus az aktuális UI-ból:
    app.setFont(QFont(UI.font_family))
    w = CountdownWindow()
    w.show()
    sys.exit(app.exec())
