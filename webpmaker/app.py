from flask import Blueprint, request, redirect, url_for, render_template, send_from_directory, send_file
import os
import zipfile
from PIL import Image
from io import BytesIO

# Blueprint létrehozása
webp_blueprint = Blueprint('webp', __name__, template_folder='../htmls')

UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'output'

webp_blueprint.config = {
    'UPLOAD_FOLDER': UPLOAD_FOLDER,
    'OUTPUT_FOLDER': OUTPUT_FOLDER
}

# A szükséges mappák létrehozása, ha még nem léteznek
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
if not os.path.exists(OUTPUT_FOLDER):
    os.makedirs(OUTPUT_FOLDER)

def convert_image_to_webp(input_path, output_path, target_size_kb=400):
    with Image.open(input_path) as img:
        original_size_kb = os.path.getsize(input_path) / 1024  # KB-ban

        if original_size_kb <= target_size_kb:
            img.save(output_path, 'WEBP')
        else:
            quality = 95
            while quality > 0:
                img.save(output_path, 'WEBP', quality=quality)
                output_size_kb = os.path.getsize(output_path) / 1024

                if output_size_kb <= target_size_kb:
                    break

                quality -= 5

@webp_blueprint.route('/', methods=['GET', 'POST'])
def upload_and_convert_images():
    if request.method == 'POST':
        if 'files' not in request.files:
            return redirect(request.url)
        files = request.files.getlist('files')
        if len(files) == 0:
            return redirect(request.url)

        converted_files = []
        for file in files:
            if file:
                filename = os.path.join(webp_blueprint.config['UPLOAD_FOLDER'], file.filename)
                file.save(filename)
                
                # Konvertálás WebP formátumba
                output_filename = os.path.splitext(file.filename)[0] + '.webp'
                output_path = os.path.join(webp_blueprint.config['OUTPUT_FOLDER'], output_filename)
                convert_image_to_webp(filename, output_path)
                converted_files.append(output_path)

        # ZIP fájl létrehozása a konvertált képekből
        zip_filename = 'converted_images.zip'
        zip_path = os.path.join(webp_blueprint.config['OUTPUT_FOLDER'], zip_filename)
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for file in converted_files:
                zipf.write(file, os.path.basename(file))

        return redirect(url_for('webp.download_zip', zip_filename=zip_filename))

    return render_template('webpmaker.html')

@webp_blueprint.route('/download_zip/<zip_filename>')
def download_zip(zip_filename):
    zip_path = os.path.join(webp_blueprint.config['OUTPUT_FOLDER'], zip_filename)
    return send_file(zip_path, as_attachment=True)