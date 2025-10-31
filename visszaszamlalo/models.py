from __future__ import annotations
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from sqlalchemy import Column, Integer, String, Boolean, Text

db = SQLAlchemy()

# --- Felhasználó ---
class User(UserMixin, db.Model):
    __tablename__ = "user"
    id = Column(Integer, primary_key=True)
    username = Column(String(150), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="user")  # 'admin' | 'user'

    def get_id(self):
        return str(self.id)

# --- Projekt ---
class Project(db.Model):
    __tablename__ = "project"
    id = Column(String(64), primary_key=True)     # kliens oldali uid
    name = Column(String(255), nullable=False)
    color = Column(String(32), nullable=False, default="#6ea8fe")
    font  = Column(String(64), nullable=False, default="default")

# --- Számláló ---
class Counter(db.Model):
    __tablename__ = "counter"
    id = Column(String(64), primary_key=True)     # kliens oldali uid
    name = Column(String(255), nullable=False)
    deadline = Column(Integer, nullable=False)    # epoch ms
    project_id = Column(String(64), nullable=True)
    archived = Column(Boolean, nullable=False, default=False)
    created_at = Column(Integer, nullable=False)  # epoch ms
    order = Column(Integer, nullable=False, default=0)

# --- ICS Naptár (tartós) ---
class Calendar(db.Model):
    __tablename__ = "calendar"
    id = Column(String(64), primary_key=True)     # kliens oldali uid ('cal_...')
    name = Column(String(255), nullable=False, default="Naptár")
    source_type = Column(String(16), nullable=False, default="inline")  # 'url' | 'inline'
    url = Column(Text, nullable=True)
    ics_text = Column(Text, nullable=False)       # teljes ICS tartalom
    created_at = Column(Integer, nullable=False)  # epoch ms
