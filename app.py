from flask import Flask, render_template, send_from_directory
import os

from bannermaker.app import bannermaker_blueprint
from categorymaker.app import category_blueprint
from matrixmaker.app import matrix_blueprint
from webpmaker.app import webp_blueprint
from keywordmaker.app import keywordmaker_blueprint

app = Flask(__name__, template_folder='.')

# Statikus fájlok kezelése a főkönyvtárból
@app.route('/<path:filename>')
def custom_static(filename):
    return send_from_directory(os.path.abspath(os.path.dirname(__file__)), filename)

# Regisztráljuk a különböző alkalmazásokat Blueprintként
app.register_blueprint(bannermaker_blueprint, url_prefix='/bannermaker')
app.register_blueprint(category_blueprint, url_prefix='/categorymaker')
app.register_blueprint(matrix_blueprint, url_prefix='/matrixmaker')
app.register_blueprint(webp_blueprint, url_prefix='/webpmaker')
app.register_blueprint(keywordmaker_blueprint, url_prefix='/keywordmaker')

# Központi oldal, amely navigációt biztosít a különböző programokhoz
@app.route('/')
def index():
    return render_template('index.html')

if __name__ == "__main__":
    app.run(debug=True)
