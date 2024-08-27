import os
import subprocess
import shutil
from flask import Blueprint, request, redirect, render_template, send_from_directory
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
ALLOWED_EXTENSIONS = {'jpg', 'jpeg'}
ZIP_FOLDER = os.path.join(os.path.dirname(__file__), 'zips')
OUTPUT_FOLDER = os.path.join(os.path.dirname(__file__), 'output_directory')

# Blueprint létrehozása
bannermaker_blueprint = Blueprint('bannermaker', __name__, template_folder='../htmls')

# Konfigurációk beállítása
bannermaker_blueprint.config = {
    'UPLOAD_FOLDER': UPLOAD_FOLDER,
    'ZIP_FOLDER': ZIP_FOLDER,
    'OUTPUT_FOLDER': OUTPUT_FOLDER
}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Routes definiálása a Blueprint-ben
@bannermaker_blueprint.route('/', methods=['GET', 'POST'])
def upload_and_run_scripts():
    font_files = [f for f in os.listdir(os.path.join(os.path.dirname(__file__), 'fonts')) if f.endswith('.ttf')]
    logo_files = [f for f in os.listdir(os.path.join(os.path.dirname(__file__), 'logos')) if f.endswith('.png')]

    if request.method == 'POST':
        # Fájl feltöltése
        if 'file' not in request.files:
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            return redirect(request.url)
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(bannermaker_blueprint.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)

            # Szövegek beolvasása
            author_name = request.form.get('author_name', 'Szerző Neve')
            book_title = request.form.get('book_title', 'Könyv hosszú címe')
            subtitle = request.form.get('subtitle', 'Rövid leírás')

            # Szín beolvasása
            chosen_color = request.form.get('chosen_color', '#ffffff')

            # Font kiválasztása
            font_choice = request.form.get('font_choice', 'Poppins-Regular.ttf')
            font_path = os.path.join(os.path.dirname(__file__), 'fonts', font_choice)

            # Logo kiválasztása
            logo_choice = request.form.get('logo_choice', 'default_logo.png')  # Feltételezve, hogy van alapértelmezett logó
            logo_path = os.path.join(os.path.dirname(__file__), 'logos', logo_choice)

            # Szkriptek futtatása
            script_directory = os.path.join(os.path.dirname(__file__), 'scripts')
            output_directory = bannermaker_blueprint.config['OUTPUT_FOLDER']

            # Ellenőrizze, hogy létezik-e az output_directory, és ha nem, hozza létre
            if not os.path.exists(output_directory):
                os.makedirs(output_directory)

            try:
                # Gyűjtse össze és futtassa a szkripteket
                scripts = [f for f in os.listdir(script_directory) if os.path.isfile(os.path.join(script_directory, f)) and f.endswith('.py')]
                for script in scripts:
                    # Futtassa a szkripteket az új argumentumokkal
                    command = f'python {os.path.join(script_directory, script)} "{file_path}" "{output_directory}" "{author_name}" "{book_title}" "{subtitle}" "{font_path}" "{logo_path}" "{chosen_color}"'

                    print(f"Futtatandó parancs: {command}")  # Ez kiírja a parancsot

                    result = subprocess.run(command, shell=True, check=True, capture_output=True)
                    print(f"Script {script} output:\n{result.stdout.decode()}")  # stdout és stderr bináris adatok, szükség lehet a decode()-ra

                    if result.stderr:
                        print(f"Script {script} errors:\n{result.stderr.decode()}")  # Kiírja az esetleges hibákat is

                # A zip fájl nevének előkészítése
                zip_name = os.path.splitext(filename)[0] + '.zip'
                zip_path = os.path.join(bannermaker_blueprint.config['ZIP_FOLDER'], zip_name)

                # Ellenőrizze, hogy létezik-e a ZIP_FOLDER, és ha nem, hozza létre
                if not os.path.exists(bannermaker_blueprint.config['ZIP_FOLDER']):
                    os.makedirs(bannermaker_blueprint.config['ZIP_FOLDER'])

                # A zip fájl létrehozása
                shutil.make_archive(os.path.splitext(zip_path)[0], 'zip', root_dir=output_directory, base_dir='.')

                # A letöltési oldalra irányítja a felhasználót
                return render_template('bannermaker.html', processing_complete=True, zip_name=zip_name, fonts=font_files, logos=logo_files)

            except subprocess.CalledProcessError as e:
                print(f"Hiba történt a parancs futtatása közben: {e}")  # Kiírja a hibaüzenetet
                print(e.output)
                return str(e)
            except Exception as e:
                print(str(e))
                return "Hiba történt a scriptek futtatása közben: " + str(e)

    # GET kérés esetén az űrlap megjelenítése
    return render_template('bannermaker.html', fonts=font_files, logos=logo_files)

@bannermaker_blueprint.route('/download_file/<filename>')
def download_file(filename):
    return send_from_directory(bannermaker_blueprint.config['ZIP_FOLDER'], filename, as_attachment=True)
