# visszaszamlalo/models.py
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='user')  # 'admin' | 'user'

    # Flask-Login kompat
    @property
    def is_authenticated(self): return True
    @property
    def is_active(self): return True
    @property
    def is_anonymous(self): return False
    def get_id(self): return str(self.id)

class Project(db.Model):
    id = db.Column(db.String(40), primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    color = db.Column(db.String(16), default='#6ea8fe')
    font = db.Column(db.String(24), default='default')

class Counter(db.Model):
    id = db.Column(db.String(40), primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    deadline = db.Column(db.BigInteger, nullable=False)  # epoch ms
    project_id = db.Column(db.String(40), db.ForeignKey('project.id'))
    project = db.relationship(Project, lazy='joined')
    archived = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.BigInteger)
    order = db.Column(db.Integer, default=0)
