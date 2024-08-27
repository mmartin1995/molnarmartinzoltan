from flask import Blueprint, request, redirect, url_for, render_template, send_from_directory
import os
from PIL import Image

# Blueprint létrehozása
webp_blueprint = Blueprint('webp', __name__, template_folder='templates')

UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'output'

webp_blueprint.config = {
    'UPLOAD_FOLDER': UPLOAD_FOLDER,
    'OUTPUT_FOLDER': OUTPUT_FOLDER
}

def convert_image_to_webp(input_path, output_path, target_size_kb=100):
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
def upload_and_convert_image():
    if request.method == 'POST':
        if 'file' not in request.files:
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            return redirect(request.url)
        if file:
            filename = os.path.join(webp_blueprint.config['UPLOAD_FOLDER'], file.filename)
            file.save(filename)
            
            # Konvertálás WebP formátumba
            output_filename = os.path.splitext(file.filename)[0] + '.webp'
            output_path = os.path.join(webp_blueprint.config['OUTPUT_FOLDER'], output_filename)
            convert_image_to_webp(filename, output_path)

            return redirect(url_for('webp.download_file', filename=output_filename))

    return render_template('webpmaker.html')

@webp_blueprint.route('/download/<filename>')
def download_file(filename):
    return send_from_directory(webp_blueprint.config['OUTPUT_FOLDER'], filename, as_attachment=True)
