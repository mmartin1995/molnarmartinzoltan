from PIL import Image, ImageDraw, ImageFilter, ImageFont
import os
from werkzeug.utils import secure_filename
import sys
import argparse
from pathlib import Path

# Előre beállított értékek
PRESET_BLUR_RADIUS = 0  # background blur mértéke
PRESET_X_POSITION = 65  #cover.jpg eltolása balról
PRESET_CORNER_RADIUS = 20  # cover.jpg sarkainak lekerekítése
PRESET_COVER_WIDTH = 400  # cover.jpg szélessége
PRESET_SHADOW_COLOR = "#000000"  # Az árnyék színe hexadecimális formátumban
PRESET_SHADOW_BLUR = 10 # Árnyék elmosásának mértéke
PRESET_SHADOW_OFFSET = (5, 5)  # Árnyék eltolása
OUTPUT_DIRECTORY = "output_directory"

# Szöveg beállítások
def get_preset_texts(author_name, book_title, subtitle):
    return [
        {
            "text": author_name,
            "font": "Poppins-Regular.ttf",
            "size": 50,
            "color": "#FFFFFF",
            "position": (540, 370)
        },
        {
            "text": book_title,
            "font": "Poppins-Regular.ttf",
            "size": 80,
            "color": "#FFFFFF",
            "position": (540, 450)
        },
        {
            "text": subtitle,
            "font": "Poppins-Regular.ttf",
            "size": 35,
            "color": "#FFFFFF",
            "position": (540, 600)
        }
    ]

def hex_to_rgba(hex_code):
    """Konvertálja a hexadecimális színkódot RGBA formátumba egy fix opacitással."""
    hex_code = hex_code.lstrip('#')
    rgba_color = tuple(int(hex_code[i:i+2], 16) for i in (0, 2, 4)) + (255,)  # Fix opacitás beállítása
    return rgba_color

def round_corners(im, rad):
    circle = Image.new('L', (rad * 2, rad * 2), 0)
    draw = ImageDraw.Draw(circle)
    draw.ellipse((0, 0, rad * 2, rad * 2), fill=255)
    alpha = Image.new('L', im.size, 255)
    w, h = im.size
    alpha.paste(circle.crop((0, 0, rad, rad)), (0, 0))
    alpha.paste(circle.crop((0, rad, rad, rad * 2)), (0, h - rad))
    alpha.paste(circle.crop((rad, 0, rad * 2, rad)), (w - rad, 0))
    alpha.paste(circle.crop((rad, rad, rad * 2, rad * 2)), (w - rad, h - rad))
    im.putalpha(alpha)
    return im

def add_shadow(image, offset=PRESET_SHADOW_OFFSET, shadow_color=None, blur_radius=PRESET_SHADOW_BLUR):
    if shadow_color is None:
        shadow_color = hex_to_rgba(PRESET_SHADOW_COLOR)

    total_offset = (offset[0] + blur_radius * 2, offset[1] + blur_radius * 2)
    shadow_size = (image.width + total_offset[0] * 2, image.height + total_offset[1] * 2)
    shadow = Image.new('RGBA', shadow_size, (0, 0, 0, 0))

    # A 'shadow_base' a teljes opacitású árnyék réteg
    shadow_base = Image.new('RGBA', shadow_size, shadow_color)

    # Az árnyékmaszk létrehozása és alkalmazása az árnyék rétegre
    shadow_mask = Image.new('L', shadow_size, 0)
    shadow_mask_draw = ImageDraw.Draw(shadow_mask)
    shadow_mask_draw.rectangle(
        [
            (total_offset[0], total_offset[1]),
            (image.width + total_offset[0], image.height + total_offset[1])
        ],
        fill=255
    )
    shadow_mask = shadow_mask.filter(ImageFilter.GaussianBlur(blur_radius))
    shadow_base.putalpha(shadow_mask)

    # A 'shadow_base' réteg beillesztése az árnyékba
    shadow.alpha_composite(shadow_base)

    # A kép beillesztése az árnyékra
    shadow.paste(
        image,
        (total_offset[0] - offset[0], total_offset[1] - offset[1]),
        image
    )

    return shadow


def resize_and_center_image(image, target_size):
    original_width, original_height = image.size
    ratio = max(target_size / original_width, target_size / original_height)
    new_width = int(original_width * ratio)
    new_height = int(original_height * ratio)

    image = image.resize((new_width, new_height), Image.LANCZOS)

    new_image = Image.new('RGBA', (target_size, target_size), (255, 255, 255, 0))
    left = (target_size - new_width) // 2
    top = (target_size - new_height) // 2
    new_image.paste(image, (left, top))

    return new_image

def blur_background(image, blur_radius):
    return image.filter(ImageFilter.GaussianBlur(blur_radius))

def add_texts(image, texts):
    """
    Hozzáadja a szöveget a képhez a megadott beállításokkal.
    """
    draw = ImageDraw.Draw(image)
    shadow_offset = (2, 2)  # Példa árnyékeltolás
    shadow_color = "#000000"  # Példa árnyékszín, ez esetben fekete

    for text_info in texts:
        try:
            font = ImageFont.truetype(text_info["font"], text_info["size"])
        except IOError:
            print(f"Hiba: A {text_info['font']} betűtípusfájl nem található. Használja az alapértelmezett betűtípust.")
            font = ImageFont.load_default()

        text = text_info["text"]
        text_color = text_info["color"]
        position = text_info["position"]
        max_width = text_info.get("max_width")

        if max_width:
            lines = wrap_text(text, font, max_width)
            line_height = font.getsize('A')[1]
            x, y = position
            for line in lines:
                # Itt rajzoljuk meg az árnyékkal ellátott szöveget
                draw_text_with_shadow(draw, line, (x, y), font, text_color, shadow_color, shadow_offset)
                y += line_height
        else:
            # Itt rajzoljuk meg az árnyékkal ellátott szöveget
            draw_text_with_shadow(draw, text, position, font, text_color, shadow_color, shadow_offset)

    return image

def draw_text_with_shadow(draw, text, position, font, text_color, shadow_color, shadow_offset):
    x, y = position
    shadow_position = (x + shadow_offset[0], y + shadow_offset[1])

    # Árnyék rajzolása
    draw.text(shadow_position, text, font=font, fill=shadow_color)

    # Szöveg rajzolása
    draw.text(position, text, font=font, fill=text_color)


def wrap_text(text, font, max_width):
    """
    Megtöri a szöveget több sorba, ha meghaladja a megadott maximális szélességet.
    """
    lines = []
    if font.getsize(text)[0] <= max_width:
        lines.append(text)
    else:
        words = text.split(' ')
        current_line = ''
        for word in words:
            test_line = current_line + word + ' '
            test_line_width = font.getsize(test_line)[0]
            if test_line_width <= max_width:
                current_line = test_line
            else:
                lines.append(current_line.strip())
                current_line = word + ' '
        if current_line:
            lines.append(current_line.strip())
    return lines

def replace_book_cover(background_path, cover_path, output_path, texts):
    background = Image.open(background_path).convert('RGBA')
    background = resize_and_center_image(background, 1080)
    background = blur_background(background, PRESET_BLUR_RADIUS)

    cover = Image.open(cover_path).convert('RGBA')
    aspect_ratio = cover.height / cover.width
    new_height = int(PRESET_COVER_WIDTH * aspect_ratio)
    cover = cover.resize((PRESET_COVER_WIDTH, new_height))

    cover_with_rounded_corners = round_corners(cover, PRESET_CORNER_RADIUS)
    cover_with_shadow = add_shadow(cover_with_rounded_corners, PRESET_SHADOW_OFFSET, None, PRESET_SHADOW_BLUR)

    y_position = (background.height - cover_with_shadow.height) // 2

    final_image = Image.new('RGBA', background.size, 0)
    final_image.paste(background, (0, 0))
    final_image.paste(cover_with_shadow, (PRESET_X_POSITION, y_position), cover_with_shadow)

    # Itt adjuk hozzá a szövegeket
    final_image = add_texts(final_image, texts)

    final_image.save(os.path.join(OUTPUT_DIRECTORY, output_path), "PNG")

# Fő program indítása
def main(input_file_path, output_directory, author_name, book_title, subtitle):
    if not os.path.exists(output_directory):
        os.makedirs(output_directory)

    preset_texts = get_preset_texts(author_name, book_title, subtitle)

    configurations = [
        {
            "background": input_file_path,
            "cover": input_file_path,
            "output": "1080output1.png"
        }
    ]

    for config in configurations:
        replace_book_cover(config["background"], config["cover"], config["output"], preset_texts)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Könyvborító kép generálása.')
    parser.add_argument('input_file_path', help='Az eredeti kép elérési útja')
    parser.add_argument('output_directory', help='A kimeneti könyvtár elérési útja')
    parser.add_argument('author_name', help='A szerző neve')
    parser.add_argument('book_title', help='A könyv címe')
    parser.add_argument('subtitle', help='A könyv alcíme')

    args = parser.parse_args()

    # Létrehozzuk a kimeneti könyvtárat, ha még nem létezik
    if not os.path.exists(args.output_directory):
        os.makedirs(args.output_directory)

    # A fő program elindítása az új argumentumokkal
    main(args.input_file_path, args.output_directory, args.author_name, args.book_title, args.subtitle)