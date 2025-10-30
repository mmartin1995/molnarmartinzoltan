# app.py (gyökér)
from flask import Flask, render_template, send_from_directory
import os

from bannermaker.app import bannermaker_blueprint
from categorymaker.app import category_blueprint
from matrixmaker.app import matrix_blueprint
from webpmaker.app import webp_blueprint
from visszaszamlalo.app import visszaszamlalo_blueprint, init_auth

app = Flask(__name__, template_folder='.')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-me')

# DB az instance/ mappában
os.makedirs(app.instance_path, exist_ok=True)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(app.instance_path, 'visszaszamlalo.sqlite')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Auth/DB init
init_auth(app)

# Statikus fájlok a gyökérből
@app.route('/<path:filename>')
def custom_static(filename):
    return send_from_directory(os.path.abspath(os.path.dirname(__file__)), filename)

# Blueprintek
app.register_blueprint(bannermaker_blueprint, url_prefix='/bannermaker')
app.register_blueprint(category_blueprint, url_prefix='/categorymaker')
app.register_blueprint(matrix_blueprint, url_prefix='/matrixmaker')
app.register_blueprint(webp_blueprint, url_prefix='/webpmaker')
app.register_blueprint(visszaszamlalo_blueprint, url_prefix='/visszaszamlalo')

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == "__main__":
    app.run(debug=True)
