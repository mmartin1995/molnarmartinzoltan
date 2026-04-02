from flask import Blueprint, request, redirect, url_for, render_template, send_file
import os
import zipfile
import uuid
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.utils import secure_filename

# Blueprint létrehozása
webp_blueprint = Blueprint('webp', __name__, template_folder='../htmls')

UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'output'

webp_blueprint.config = {
    'UPLOAD_FOLDER': UPLOAD_FOLDER,
    'OUTPUT_FOLDER': OUTPUT_FOLDER
}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)


def _normalize_image_mode(img: Image.Image) -> Image.Image:
    """
    - EXIF orientáció javítás (telefonos képeknél gyakori)
    - WebP-hez praktikusan RGB / RGBA módra hozunk mindent
    """
    img = ImageOps.exif_transpose(img)

    if img.mode in ("RGB", "RGBA"):
        return img
    if "A" in img.getbands():
        return img.convert("RGBA")
    return img.convert("RGB")


def validate_image_file(path: str) -> tuple[bool, str | None]:
    """
    Valódi kép-e:
    - img.verify(): alap integritás ellenőrzés (nem dekódol mindent)
    - img.load(): tényleges dekódolás (sok “álkép” itt bukik meg)
    """
    try:
        with Image.open(path) as img:
            img.verify()

        with Image.open(path) as img:
            img.load()

        return True, None
    except (UnidentifiedImageError, OSError, ValueError) as e:
        return False, str(e)


def convert_image_to_webp_max_size(
    input_path: str,
    output_path: str,
    target_size_kb: int,
    start_quality: int = 95,
    step: int = 2,
    min_quality: int = 1
) -> int:
    target_size_kb = max(1, int(target_size_kb))
    start_quality = max(1, min(100, int(start_quality)))
    step = max(1, int(step))
    min_quality = max(1, min(100, int(min_quality)))

    with Image.open(input_path) as img:
        img = _normalize_image_mode(img)

        original_size_kb = os.path.getsize(input_path) / 1024
        if original_size_kb <= target_size_kb:
            img.save(output_path, 'WEBP', quality=start_quality, method=6)
            return start_quality

        quality = start_quality
        while quality >= min_quality:
            img.save(output_path, 'WEBP', quality=quality, method=6)
            output_size_kb = os.path.getsize(output_path) / 1024

            if output_size_kb <= target_size_kb:
                return quality

            quality -= step

        img.save(output_path, 'WEBP', quality=min_quality, method=6)
        return min_quality


def convert_image_to_webp_target_quality(input_path: str, output_path: str, quality_percent: int) -> int:
    quality = max(1, min(100, int(quality_percent)))

    with Image.open(input_path) as img:
        img = _normalize_image_mode(img)
        img.save(output_path, 'WEBP', quality=quality, method=6)

    return quality


@webp_blueprint.route('/', methods=['GET', 'POST'])
def upload_and_convert_images():
    if request.method == 'POST':
        if 'files' not in request.files:
            return redirect(request.url)

        files = request.files.getlist('files')
        if not files:
            return redirect(request.url)

        mode = request.form.get('mode', 'max_size')  # "max_size" vagy "target_quality"
        max_size_kb = request.form.get('max_size_kb', type=int, default=400)
        target_quality = request.form.get('target_quality', type=int, default=95)

        converted_files: list[str] = []
        errors: list[str] = []

        for file in files:
            if not file or not file.filename:
                continue

            original_name = file.filename
            safe_name = secure_filename(original_name)

            input_path = os.path.join(webp_blueprint.config['UPLOAD_FOLDER'], safe_name)
            file.save(input_path)

            # VALIDÁLÁS: tényleg kép-e?
            ok, err = validate_image_file(input_path)
            if not ok:
                try:
                    os.remove(input_path)
                except Exception:
                    pass
                errors.append(f"❌ {original_name} – nem érvényes kép ({err})")
                continue

            base = os.path.splitext(safe_name)[0]
            unique = uuid.uuid4().hex[:8]  # ütközés ellen

            # temp kimenet
            tmp_output_filename = f"{base}_tmp_{unique}.webp"
            tmp_output_path = os.path.join(webp_blueprint.config['OUTPUT_FOLDER'], tmp_output_filename)

            try:
                if mode == 'target_quality':
                    used_q = convert_image_to_webp_target_quality(input_path, tmp_output_path, target_quality)
                else:
                    used_q = convert_image_to_webp_max_size(
                        input_path, tmp_output_path, max_size_kb, start_quality=95, step=2
                    )

                final_output_filename = f"{base}_q{used_q}_{unique}.webp"
                final_output_path = os.path.join(webp_blueprint.config['OUTPUT_FOLDER'], final_output_filename)

                if os.path.exists(tmp_output_path):
                    os.replace(tmp_output_path, final_output_path)

                converted_files.append(final_output_path)

            except Exception as e:
                # hibás kép/konverzió esetén
                try:
                    if os.path.exists(tmp_output_path):
                        os.remove(tmp_output_path)
                except Exception:
                    pass
                errors.append(f"❌ {original_name} – konvertálás sikertelen ({e})")
                continue

        # Ha semmi nem sikerült, marad a form + hibák
        if not converted_files:
            return render_template(
                'webpmaker.html',
                errors=errors,
                download_url=None,
                converted_count=0,
                mode=mode,
                max_size_kb=max_size_kb,
                target_quality=target_quality
            )

        # ZIP készítés
        zip_filename = f'converted_images_{uuid.uuid4().hex}.zip'
        zip_path = os.path.join(webp_blueprint.config['OUTPUT_FOLDER'], zip_filename)

        with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zipf:
            for fpath in converted_files:
                zipf.write(fpath, os.path.basename(fpath))

        download_url = url_for('webp.download_zip', zip_filename=zip_filename)

        # Itt nem redirectelünk azonnal, hogy ki tudjuk írni a hibákat a felületen
        return render_template(
            'webpmaker.html',
            errors=errors,
            download_url=download_url,
            converted_count=len(converted_files),
            mode=mode,
            max_size_kb=max_size_kb,
            target_quality=target_quality
        )

    # GET
    return render_template(
        'webpmaker.html',
        errors=[],
        download_url=None,
        converted_count=0,
        mode='max_size',
        max_size_kb=400,
        target_quality=95
    )


@webp_blueprint.route('/download_zip/<zip_filename>')
def download_zip(zip_filename):
    zip_path = os.path.join(webp_blueprint.config['OUTPUT_FOLDER'], zip_filename)
    return send_file(zip_path, as_attachment=True)
