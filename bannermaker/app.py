import os
import subprocess
from flask import Flask, request, redirect, url_for, render_template
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'jpg', 'jpeg'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        if 'file' not in request.files:
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            return redirect(request.url)
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            return render_template('run_scripts.html', filename=filename)
    return render_template('upload.html')

@app.route('/run-scripts', methods=['POST'])
def run_scripts():
    filename = request.form['filename']
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    script_directory = 'scripts'  # A scriptek könyvtára

    # Beolvassa a scriptek könyvtárát
    try:
        scripts = [f for f in os.listdir(script_directory) if os.path.isfile(os.path.join(script_directory, f)) and f.endswith('.py')]
        for script in scripts:
            subprocess.run(['python', os.path.join(script_directory, script), file_path], check=True)

        return render_template('scripts_run_success.html')
    except subprocess.CalledProcessError as e:
        # Nyomtassa ki a hibát, hogy könnyebb legyen azonosítani a problémát
        print(e.output)
        return str(e)
    except Exception as e:
        # Általános kivételkezelés, ha más típusú hiba történik
        print(str(e))
        return "Hiba történt a scriptek futtatása közben: " + str(e)

if __name__ == "__main__":
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    app.run(debug=True)
