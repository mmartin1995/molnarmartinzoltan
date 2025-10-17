# app.py — 2× képnagyítás + minőségjavítás + "nem-puhulhat" részlet-injekció
# Telepítés (ajánlott):
#   python -m venv venv
#   source venv/bin/activate    # Windows: venv\Scripts\activate
#   pip install flask pillow opencv-contrib-python requests

import io
import os
import pathlib
import tempfile
import requests
import numpy as np
from werkzeug.utils import secure_filename
from flask import Flask, request, send_file, render_template_string, abort
from PIL import Image

# OpenCV (contrib) — AI szuperfelbontás + minőségjavítás
try:
    import cv2  # type: ignore
    OPENCV_OK = True
except Exception:
    OPENCV_OK = False

APP = Flask(__name__)
APP.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # max 50 MB
ALLOWED_EXT = {"jpg", "jpeg", "png", "webp", "tif", "tiff", "bmp"}

# --- UI (egyszerű űrlap) ------------------------------------------------------
HTML = """
<!doctype html>
<title>2× Képnagyító + Minőségjavító</title>
<meta name="viewport" content="width=device-width,initial-scale=1" />
<style>
  body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; max-width: 760px; margin: 40px auto; padding: 0 16px; }
  .card { border: 1px solid #e5e7eb; border-radius: 14px; padding: 20px; box-shadow: 0 1px 8px rgba(0,0,0,.04); }
  .row { display:flex; gap:12px; align-items:center; }
  input[type=file] { padding: 10px; border:1px solid #e5e7eb; border-radius:10px; width:100%; }
  button { padding: 12px 18px; border:none; border-radius:12px; cursor:pointer; font-weight:600; }
  .primary { background:#111827; color:white; }
  .hint { color:#6b7280; font-size:.95rem; }
  .small { font-size: .9rem; color:#6b7280; margin-top:10px; }
  .warn { margin-top: 10px; color: #b45309; }
</style>
<div class="card">
  <h1>2× képnagyítás + automatikus minőségjavítás</h1>
  <p class="hint">AI-alapú (EDSR x2) nagyítást használ, ha elérhető. Zajcsökkentés (adaptív), lokális kontraszt (CLAHE), fehéregyensúly, Luma-élesítés, adaptív gamma, és <b>részlet-injekció</b> az eredetiből, hogy ne puhítson.</p>
  <form class="row" method="post" action="/upscale" enctype="multipart/form-data">
    <input type="file" name="image" required />
    <button class="primary" type="submit">Felnagyít & Javít</button>
  </form>
  <p class="small">Támogatott: JPG, PNG, WEBP, TIFF, BMP. Alfa csatorna megőrizve.</p>
  %OPENCV_WARN%
</div>
"""

def is_allowed(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT

# --- Modelletöltés (EDSR x2) --------------------------------------------------
MODEL_DIR = pathlib.Path(".models")
MODEL_DIR.mkdir(exist_ok=True)
EDSR_X2_PB = MODEL_DIR / "EDSR_x2.pb"
MODEL_URLS = [
    "https://github.com/opencv/opencv_contrib/raw/4.x/modules/dnn_superres/samples/dnn_superres/models/EDSR_x2.pb",
    "https://github.com/Saafke/EDSR_Tensorflow/raw/master/models/EDSR_x2.pb",
]

def ensure_model() -> bool:
    if not OPENCV_OK:
        return False
    if EDSR_X2_PB.exists():
        return True
    for url in MODEL_URLS:
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            EDSR_X2_PB.write_bytes(r.content)
            return True
        except Exception:
            continue
    return False

# --- Képkonverziók ------------------------------------------------------------
def _to_bgr(img: Image.Image) -> np.ndarray:
    """PIL -> BGR(A) uint8 (OpenCV)"""
    if not OPENCV_OK:
        raise RuntimeError("OpenCV szükséges ehhez a konverzióhoz.")
    if img.mode == "RGBA":
        arr = np.array(img, dtype=np.uint8)
        return cv2.cvtColor(arr, cv2.COLOR_RGBA2BGRA)
    if img.mode == "RGB":
        arr = np.array(img, dtype=np.uint8)
        return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    if img.mode == "L":
        arr = np.array(img, dtype=np.uint8)
        return cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
    arr = np.array(img.convert("RGBA"), dtype=np.uint8)
    return cv2.cvtColor(arr, cv2.COLOR_RGBA2BGRA)

def _to_pil(bgr: np.ndarray) -> Image.Image:
    """BGR(A) uint8 -> PIL"""
    if bgr.ndim == 3 and bgr.shape[2] == 4:
        rgba = cv2.cvtColor(bgr, cv2.COLOR_BGRA2RGBA)
        return Image.fromarray(rgba, mode="RGBA")
    if bgr.ndim == 3:
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb, mode="RGB")
    return Image.fromarray(bgr, mode="L")

# --- AI szuperfelbontás (EDSR x2) --------------------------------------------
def upscale_opencv_edsr_x2(img_bgr: np.ndarray) -> np.ndarray | None:
    """BGR vagy BGRA → EDSR x2. Alfa csatornát külön skálázza és visszateszi."""
    if not OPENCV_OK:
        return None
    if not ensure_model():
        return None
    try:
        alpha = None
        base = img_bgr
        if img_bgr.ndim == 3 and img_bgr.shape[2] == 4:
            alpha = img_bgr[:, :, 3]
            base = img_bgr[:, :, :3]

        sr = cv2.dnn_superres.DnnSuperResImpl_create()
        sr.readModel(str(EDSR_X2_PB))
        sr.setModel("edsr", 2)
        up_bgr = sr.upsample(base)

        if alpha is not None:
            up_a = cv2.resize(alpha, (up_bgr.shape[1], up_bgr.shape[0]), interpolation=cv2.INTER_LANCZOS4)
            return np.dstack([up_bgr, up_a])
        return up_bgr
    except Exception:
        return None

# --- Fallback skálázás (Pillow/Lanczos) --------------------------------------
def upscale_lanczos_2x(pil_img: Image.Image) -> Image.Image:
    w, h = pil_img.size
    return pil_img.resize((w * 2, h * 2), resample=Image.Resampling.LANCZOS)

# --- Minőségjavító építőkockák (OpenCV) --------------------------------------
def estimate_noise_sigma(gray: np.ndarray) -> float:
    gray = gray.astype(np.float32)
    H = cv2.Laplacian(gray, cv2.CV_32F, ksize=3)
    sigma = float(np.median(np.abs(H))) / 0.6745
    return sigma

def denoise_adaptive(bgr: np.ndarray) -> np.ndarray:
    """Csak zajos képen denoise-ol; éleket megőrzi."""
    has_alpha = (bgr.ndim == 3 and bgr.shape[2] == 4)
    base = bgr[:, :, :3] if has_alpha else bgr
    gray = cv2.cvtColor(base, cv2.COLOR_BGR2GRAY)
    s = estimate_noise_sigma(gray)
    if s < 3.0:
        return bgr  # tiszta: ne lágyítsunk
    h = float(np.clip(np.interp(s, [3, 10, 25], [3, 6, 9]), 0, 12))
    d = cv2.fastNlMeansDenoisingColored(base, None, h, max(h - 1, 0), 7, 21)
    return np.dstack([d, bgr[:, :, 3]]) if has_alpha else d

def clahe_luma(bgr: np.ndarray, clip=1.6, tiles=(8, 8)) -> np.ndarray:
    """Lokális kontraszt (CLAHE) csak az L csatornán."""
    alpha = None
    base = bgr
    if bgr.ndim == 3 and bgr.shape[2] == 4:
        alpha = bgr[:, :, 3]
        base = bgr[:, :, :3]
    lab = cv2.cvtColor(base, cv2.COLOR_BGR2LAB)
    L, A, B = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=clip, tileGridSize=tiles)
    L2 = clahe.apply(L)
    out = cv2.cvtColor(cv2.merge([L2, A, B]), cv2.COLOR_LAB2BGR)
    if alpha is not None:
        out = np.dstack([out, alpha])
    return out

def gray_world_white_balance(bgr: np.ndarray) -> np.ndarray:
    """Egyszerű gray-world fehéregyensúly (alfa megtartva)."""
    if bgr.ndim != 3:
        return bgr
    alpha = None
    base = bgr
    if bgr.shape[2] == 4:
        alpha = bgr[:, :, 3]
        base = bgr[:, :, :3]
    b, g, r = cv2.split(base.astype(np.float32))
    eps = 1e-6
    mb, mg, mr = b.mean() + eps, g.mean() + eps, r.mean() + eps
    m = (mb + mg + mr) / 3.0
    b = np.clip(b * (m / mb), 0, 255)
    g = np.clip(g * (m / mg), 0, 255)
    r = np.clip(r * (m / mr), 0, 255)
    out = cv2.merge([b, g, r]).astype(np.uint8)
    if alpha is not None:
        out = np.dstack([out, alpha])
    return out

def edge_aware_sharpen_luma(bgr: np.ndarray, amount=0.75, radius=0.9, threshold=2) -> np.ndarray:
    """Él-tudatos élesítés csak L csatornán (szín-halo nélkül)."""
    has_alpha = (bgr.ndim == 3 and bgr.shape[2] == 4)
    base = bgr[:, :, :3] if has_alpha else bgr
    lab = cv2.cvtColor(base, cv2.COLOR_BGR2LAB)
    L, A, B = cv2.split(lab)
    blur = cv2.GaussianBlur(L, (0, 0), radius)
    detail = cv2.subtract(L, blur)
    mask = (np.abs(detail) > threshold).astype(np.float32)
    mask = cv2.GaussianBlur(mask, (0, 0), 0.8)
    L2 = np.clip(L.astype(np.float32) + amount * detail.astype(np.float32) * mask, 0, 255).astype(np.uint8)
    out = cv2.cvtColor(cv2.merge([L2, A, B]), cv2.COLOR_LAB2BGR)
    return np.dstack([out, bgr[:, :, 3]]) if has_alpha else out

def boost_saturation_and_gamma(
    bgr: np.ndarray,
    sat=1.04,
    gamma=None,
    target_mean=0.48,
    gamma_bounds=(0.85, 1.10),
) -> np.ndarray:
    """
    Enyhe szaturáció + ADAPTÍV gamma:
    - Ha gamma=None, a V csatorna átlagát a target_mean környékére hozza.
    - gamma < 1 -> világosít, gamma > 1 -> sötétít.
    """
    has_alpha = (bgr.ndim == 3 and bgr.shape[2] == 4)
    base = bgr[:, :, :3] if has_alpha else bgr

    hsv = cv2.cvtColor(base, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)
    s = np.clip(s.astype(np.float32) * sat, 0, 255).astype(np.uint8)

    v_norm = v.astype(np.float32) / 255.0
    mean_v = float(v_norm.mean())
    if gamma is None:
        eps = 1e-6
        g = np.log(max(target_mean, eps)) / np.log(max(mean_v, eps))
        g = float(np.clip(g, gamma_bounds[0], gamma_bounds[1]))
    else:
        g = float(gamma)

    lut = ((np.arange(256, dtype=np.float32) / 255.0) ** g * 255.0).clip(0, 255).astype(np.uint8)
    v2 = cv2.LUT(v, lut)

    hsv2 = cv2.merge([h, s, v2])
    base2 = cv2.cvtColor(hsv2, cv2.COLOR_HSV2BGR)
    if has_alpha:
        base2 = np.dstack([base2, bgr[:, :, 3]])
    return base2

def inject_original_details(orig_bgr: np.ndarray, upscaled_bgr: np.ndarray, amount=0.55, radius=0.9) -> np.ndarray:
    """
    "Nem-puhulhat" garancia: az eredeti L-csatorna részleteit 2×-re skálázva
    visszakeveri az upscalelt kép L csatornájába (élmaszkkal).
    """
    if orig_bgr is None or upscaled_bgr is None:
        return upscaled_bgr

    up_has_alpha = (upscaled_bgr.ndim == 3 and upscaled_bgr.shape[2] == 4)
    up_base = upscaled_bgr[:, :, :3] if up_has_alpha else upscaled_bgr

    orig_base = orig_bgr[:, :, :3] if (orig_bgr.ndim == 3 and orig_bgr.shape[2] == 4) else orig_bgr

    lab_o = cv2.cvtColor(orig_base, cv2.COLOR_BGR2LAB)
    L_o, A_o, B_o = cv2.split(lab_o)
    L_blur = cv2.GaussianBlur(L_o, (0, 0), radius)
    L_detail = (L_o.astype(np.float32) - L_blur.astype(np.float32))

    edges = cv2.Laplacian(L_o, cv2.CV_32F, ksize=3)
    edges = np.abs(edges)
    p95 = max(1.0, float(np.percentile(edges, 95)))
    mask = np.clip(edges / p95, 0, 1)
    mask = cv2.GaussianBlur(mask, (0, 0), 0.8)

    H, W = up_base.shape[:2]
    L_detail_2x = cv2.resize(L_detail, (W, H), interpolation=cv2.INTER_LANCZOS4)
    mask_2x = cv2.resize(mask, (W, H), interpolation=cv2.INTER_CUBIC)

    lab_u = cv2.cvtColor(up_base, cv2.COLOR_BGR2LAB)
    L_u, A_u, B_u = cv2.split(lab_u)
    L_u2 = np.clip(L_u.astype(np.float32) + amount * L_detail_2x * mask_2x, 0, 255).astype(np.uint8)
    out_base = cv2.cvtColor(cv2.merge([L_u2, A_u, B_u]), cv2.COLOR_LAB2BGR)

    if up_has_alpha:
        return np.dstack([out_base, upscaled_bgr[:, :, 3]])
    return out_base

def improve_quality_bgr(bgr: np.ndarray) -> np.ndarray:
    """Teljes minőségjavító lánc (OpenCV-vel)."""
    out = denoise_adaptive(bgr)                     # csak ha tényleg zajos
    out = clahe_luma(out, clip=1.6, tiles=(8, 8))   # óvatos CLAHE
    out = gray_world_white_balance(out)             # természetesebb színek
    out = edge_aware_sharpen_luma(out, amount=0.75, radius=0.9, threshold=2)  # luma-élesítés
    out = boost_saturation_and_gamma(out, sat=1.04, gamma=None, target_mean=0.48)  # adaptív gamma
    return out

# --- Mentés a forrásformátumhoz igazodva -------------------------------------
def save_image_like_source(pil_img: Image.Image, src_name: str):
    ext = src_name.rsplit(".", 1)[1].lower() if "." in src_name else "png"
    bio = io.BytesIO()
    if ext in {"jpg", "jpeg"}:
        pil_img.save(bio, format="JPEG", quality=95, subsampling=0, optimize=True)
        mime = "image/jpeg"; out_ext = "jpg"
    elif ext in {"png"}:
        pil_img.save(bio, format="PNG", optimize=True)
        mime = "image/png"; out_ext = "png"
    elif ext in {"webp"}:
        pil_img.save(bio, format="WEBP", quality=95, method=6)
        mime = "image/webp"; out_ext = "webp"
    elif ext in {"tif", "tiff"}:
        pil_img.save(bio, format="TIFF", compression="tiff_lzw")
        mime = "image/tiff"; out_ext = "tiff"
    else:
        pil_img.save(bio, format="PNG", optimize=True)
        mime = "image/png"; out_ext = "png"
    bio.seek(0)
    return bio.read(), mime, out_ext

# --- Flask route-ok -----------------------------------------------------------
@APP.route("/", methods=["GET"])
def index():
    warn = ""
    if not OPENCV_OK:
        warn = '<p class="warn">Figyelem: az OpenCV nincs telepítve. A minőségjavító lépések korlátozottak lesznek (csak Lanczos + alap élesítés).</p>'
    return render_template_string(HTML.replace("%OPENCV_WARN%", warn))

@APP.route("/upscale", methods=["POST"])
def upscale():
    if "image" not in request.files:
        abort(400, "Hiányzik a 'image' mező.")
    file = request.files["image"]
    if file.filename == "":
        abort(400, "Nem választottál ki fájlt.")
    if not is_allowed(file.filename):
        abort(400, "Csak JPG, JPEG, PNG, WEBP, TIFF, BMP engedélyezett.")

    filename = secure_filename(file.filename)
    suffix = pathlib.Path(filename).suffix.lower()

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        file.save(tmp.name)
        temp_path = tmp.name

    try:
        # --- Ha van OpenCV, teljes AI + minőségjavító pipeline ---
        if OPENCV_OK:
            orig_bgr = cv2.imread(temp_path, cv2.IMREAD_UNCHANGED)

            up_pil = None
            up = None

            # 1) Próbáljuk AI EDSR x2-t
            if orig_bgr is not None:
                up = upscale_opencv_edsr_x2(orig_bgr)

            # 2) Ha nem sikerült, Lanczos (Pillow) 2×, majd konverzió BGR-re
            if up is None:
                with Image.open(temp_path) as im:
                    if im.mode not in ("RGB", "RGBA", "L"):
                        im = im.convert("RGBA")
                    up_img = upscale_lanczos_2x(im)
                up = _to_bgr(up_img)

            # 3) Minőségjavítás + "nem-puhulhat" részlet-injekció
            up = improve_quality_bgr(up)
            up = inject_original_details(orig_bgr, up, amount=0.55, radius=0.9)

            up_pil = _to_pil(up)

        # --- Ha nincs OpenCV, egyszerű (Pillow) fallback ---
        else:
            with Image.open(temp_path) as im:
                if im.mode not in ("RGB", "RGBA", "L"):
                    im = im.convert("RGBA")
                up_img = upscale_lanczos_2x(im)
                # Enyhe Unsharp a lágyulás ellen (Pillow)
                from PIL import ImageFilter
                up_img = up_img.filter(ImageFilter.UnsharpMask(radius=1.0, percent=80, threshold=2))
                up_pil = up_img

        # Mentés
        data, mime, out_ext = save_image_like_source(up_pil, filename)
        stem = pathlib.Path(filename).stem
        out_name = f"{stem}_2x_enhanced.{out_ext}"

        return send_file(io.BytesIO(data), mimetype=mime, as_attachment=True, download_name=out_name)

    finally:
        try:
            os.remove(temp_path)
        except Exception:
            pass

# --- Futtatás -----------------------------------------------------------------
if __name__ == "__main__":
    # Helyi futtatás: python app.py  → http://127.0.0.1:5000
    APP.run(host="127.0.0.1", port=5000, debug=False)