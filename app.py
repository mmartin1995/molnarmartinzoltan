from flask import Flask, render_template
from bannermaker.app import banner_blueprint
from categorymaker.app import category_blueprint
from matrixmaker.app import matrix_blueprint
from webpmaker.app import webp_blueprint

app = Flask(__name__)

# Regisztráljuk a különböző alkalmazásokat Blueprintként
app.register_blueprint(banner_blueprint, url_prefix='/bannermaker')
app.register_blueprint(category_blueprint, url_prefix='/categorymaker')
app.register_blueprint(matrix_blueprint, url_prefix='/matrixmaker')
app.register_blueprint(webp_blueprint, url_prefix='/webpmaker')

# Központi oldal, amely navigációt biztosít a különböző programokhoz
@app.route('/')
def index():
    return render_template('index.html')

if __name__ == "__main__":
    app.run()