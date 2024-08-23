from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageStat, ImageChops
from sklearn.cluster import KMeans
import os
import sys
import argparse
import numpy as np

# ELŐRE BEÁLLÍTOTT ÉRTÉKEK
PRESET_BLUR_RADIUS = 20  # background blur mértéke
PRESET_CORNER_RADIUS = 15 # cover.jpg sarkainak lekerekítése
PRESET_COVER_WIDTH = 600 # cover.jpg szélessége
PRESET_SHADOW_COLOR = "#000000"  # Az árnyék színe hexadecimális formátumban
PRESET_SHADOW_BLUR = 10 # Árnyék elmosásának mértéke a cover mögött
PRESET_SHADOW_OFFSET = (5, 5)  # Árnyék eltolása
OUTPUT_DIRECTORY = "output_directory"
PRESET_SQUARE_OPACITY = 70  # opacitás százalékban - négyzet
PRESET_BANNER_WIDTH = 1080 # a banner szélessége
PRESET_BANNER_HEIGHT = 1920 # a banner magassága
PRESET_SQUARE_RADIUS = 20 # négyzet lekerekítése pixelben
PRESET_COVER_Y_POSITION = 180 # borító eltolása fentről
PRESET_COVER_X_POSITION = (PRESET_BANNER_WIDTH - PRESET_COVER_WIDTH) // 2 #cover.jpg eltolása balról

# SZÖVEGEK
# Általános
PRESET_TEXT_MAX_WIDTH = 800 # szövegek max szélessége
PRESET_TEXT_X_POSITION = (PRESET_BANNER_WIDTH - PRESET_TEXT_MAX_WIDTH) // 2 # szövegek bal oldalról eltolása pixelben
PRESET_TEXTSHADOW_BLUR = 1 # Szövegek mögötti árnyékolás blur értéke
PRESET_TEXTSHADOW_OPACITY = 60  # Példa: 50% opacitás
PRESET_TEXT_OUTLINE_WIDTH = 1    # A kontúr vastagsága

# Szerző neve
PRESET_AUTHOR_NAME_Y_POSITION = 1150 #
PRESET_AUTHOR_NAME_MAX_HEIGHT = 70 #

# Könyv címe
PRESET_BOOK_TITLE_Y_POSITION = 1250 #
PRESET_BOOK_TITLE_MAX_HEIGHT = 240 #

# Könyv rövid leírása
PRESET_SUBTITLE_Y_POSITION = 1490 #
PRESET_SUBTITLE_MAX_HEIGHT = 280 #

def get_dominant_color(image, num_clusters=5):
    # A kép átalakítása RGB formátumba
    image = image.convert('RGB')

    # A kép pixeladatainak lekérdezése
    pixels = list(image.getdata())

    # K-means clustering alkalmazása a színek csoportosításához,
    # explicit módon állítva az 'n_init' paramétert
    kmeans = KMeans(n_clusters=num_clusters, n_init=10)
    kmeans.fit(pixels)

    # Meghatározza a központokat (centroids)
    centroids = kmeans.cluster_centers_

    # A leggyakoribb csoport középpontjának meghatározása
    labels = kmeans.labels_
    most_common_label = np.argmax(np.bincount(labels))
    most_common = centroids[most_common_label]
    return tuple(int(x) for x in most_common[:3])  # Csak az RGB értékek visszaadása


def hex_to_rgba(hex_code):
    """Konvertálja a hexadecimális színkódot RGBA formátumba a megadott opacitással."""
    hex_code = hex_code.lstrip('#')
    rgba_color = tuple(int(hex_code[i:i+2], 16) for i in (0, 2, 4))
    return rgba_color

def round_corners(im, rad):
    width, height = im.size

    # Létrehoz egy alfa maszkot, amely kezdetben teljesen opak
    alpha = Image.new('L', (width, height), 255)

    # Létrehoz egy kör alakú maszkot a lekerekítéshez
    corner = Image.new('L', (rad * 2, rad * 2), 0)
    corner_draw = ImageDraw.Draw(corner)
    corner_draw.ellipse((0, 0, rad * 2, rad * 2), fill=255)

    # A kör alakú maszkot a négy sarokra alkalmazza
    alpha.paste(corner.crop((0, 0, rad, rad)), (0, 0))
    alpha.paste(corner.crop((0, rad, rad, rad * 2)), (0, height - rad))
    alpha.paste(corner.crop((rad, 0, rad * 2, rad)), (width - rad, 0))
    alpha.paste(corner.crop((rad, rad, rad * 2, rad * 2)), (width - rad, height - rad))

    # A kép meglévő alfa csatornájának (ha van) kombinálása az új maszkkal
    if im.mode == 'RGBA':
        original_alpha = im.split()[3]
        alpha = ImageChops.multiply(alpha, original_alpha)

    im.putalpha(alpha)
    return im


def add_shadow(image, offset=PRESET_SHADOW_OFFSET, shadow_color=None, blur_radius=PRESET_SHADOW_BLUR):
    if shadow_color is None:
        shadow_color = PRESET_SHADOW_COLOR

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


def replace_book_cover(background_path, cover_path, output_path, texts, output_directory, logo_path, color_code, book_title):
    background = Image.open(background_path).convert('RGBA')
    background = resize_and_center_image(background)
    background = blur_background(background, PRESET_BLUR_RADIUS)

    cover = Image.open(cover_path).convert('RGBA')
    aspect_ratio = cover.height / cover.width
    new_height = int(PRESET_COVER_WIDTH * aspect_ratio)
    cover = cover.resize((PRESET_COVER_WIDTH, new_height))

    cover_with_rounded_corners = round_corners(cover, PRESET_CORNER_RADIUS)
    cover_with_shadow = add_shadow(cover_with_rounded_corners, PRESET_SHADOW_OFFSET, None, PRESET_SHADOW_BLUR)

    final_image = Image.new('RGBA', (PRESET_BANNER_WIDTH, PRESET_BANNER_HEIGHT), 0)
    final_image.paste(background, (0, 0))

    # A borító színének meghatározása és az alfa érték kiszámítása
    dominant_color = get_dominant_color(cover)
    alpha_value = int(PRESET_SQUARE_OPACITY * 255 / 100)

    # Az átlátszó kép létrehozása a négyzet rajzolásához
    transparent_image = Image.new('RGBA', final_image.size, (0, 0, 0, 0))

    # A négyzet méretének és pozíciójának meghatározása
    square_width = int(PRESET_TEXT_MAX_WIDTH + PRESET_SQUARE_RADIUS + 25)
    x_square_position = int((PRESET_BANNER_WIDTH - square_width) / 2) 
    y_square_position = int((PRESET_COVER_Y_POSITION + cover.height) - 10)
    square_position = (x_square_position, y_square_position)
    square_height = int(PRESET_SUBTITLE_Y_POSITION + PRESET_SUBTITLE_MAX_HEIGHT - y_square_position)

    # Létrehozzuk a négyzetet és lekerekítjük a sarkait
    square_color = dominant_color + (alpha_value,)  # RGBA szín létrehozása
    square = Image.new('RGBA', (square_width, square_height), square_color)
    square = round_corners(square, PRESET_SQUARE_RADIUS)

    # A lekerekített négyzet helyezése az átlátszó képre
    transparent_image.paste(square, square_position, square)

    # A négyzet hozzáadása a fő képhez
    final_image.alpha_composite(transparent_image, (0,0))

    # A borító hozzáadása a négyzet fölé
    y_position = PRESET_COVER_Y_POSITION
    final_image.paste(cover_with_shadow, (PRESET_COVER_X_POSITION, y_position), cover_with_shadow)

    # Itt adjuk hozzá a szövegeket
    final_image = add_texts(final_image, texts, book_title)
    
    # Logó hozzáadása
    final_image = add_logo(final_image, logo_path, color_code)

    final_image.save(os.path.join(output_directory, output_path), "PNG")


# Szöveg beállítások
def get_preset_texts(author_name, book_title, subtitle, font_path, color_code):
    return [
        {
            "text": author_name,
            "font": font_path,
            "size": 60,
            "max_height": PRESET_AUTHOR_NAME_MAX_HEIGHT,
            "color": color_code,
            "position": (PRESET_TEXT_X_POSITION, PRESET_AUTHOR_NAME_Y_POSITION),
            "max_width": PRESET_TEXT_MAX_WIDTH,
            "line_spacing": 5
        },
        {
            "text": book_title,
            "font": font_path,
            "size": 120,
            "max_height": PRESET_BOOK_TITLE_MAX_HEIGHT,
            "color": color_code,
            "position": (PRESET_TEXT_X_POSITION, PRESET_BOOK_TITLE_Y_POSITION),
            "max_width": PRESET_TEXT_MAX_WIDTH,
            "line_spacing": 10
        },
        {
            "text": subtitle,
            "font": font_path,
            "size": 40,
            "max_height": PRESET_SUBTITLE_MAX_HEIGHT,
            "color": color_code,
            "position": (PRESET_TEXT_X_POSITION, PRESET_SUBTITLE_Y_POSITION),
            "max_width": PRESET_TEXT_MAX_WIDTH,
            "line_spacing": 20
        }
    ]

# Függvény a betűméret dinamikus kiszámítására
def calculate_font_size(font_path, max_size, max_width, max_height, text, line_spacing):
    font_size = max_size
    font = ImageFont.truetype(font_path, font_size)
    total_height = 0

    while font_size > 1:
        lines, total_height = wrap_text(text, font_path, max_width, max_height, font_size, line_spacing)
        if total_height <= max_height:
            return font_size
        font_size -= 1

    return font_size


def resize_and_center_image(image):
    original_width, original_height = image.size
    target_width = PRESET_BANNER_WIDTH
    target_height = PRESET_BANNER_HEIGHT
    ratio = max(target_width / original_width, target_height / original_height)
    new_width = int(original_width * ratio)
    new_height = int(original_height * ratio)

    image = image.resize((new_width, new_height), Image.LANCZOS)

    new_image = Image.new('RGBA', (target_width, target_height), (255, 255, 255, 0))
    left = (target_width - new_width) // 2
    top = (target_height - new_height) // 2
    new_image.paste(image, (left, top))

    return new_image

def blur_background(image, blur_radius):
    return image.filter(ImageFilter.GaussianBlur(blur_radius))

def draw_text_with_outline(draw, text, position, font, text_color, outline_width):
    x, y = position
    outline_color = text_color  # A kontúr színe megegyezik a szöveg színével

    # Körvonal rajzolása csak jobbra
    draw.text((x + outline_width, y), text, font=font, fill=outline_color)

    # Fő szöveg rajzolása
    draw.text(position, text, font=font, fill=text_color)

def add_texts(image, texts, book_title):
    draw = ImageDraw.Draw(image)
    shadow_offset = (0.1, 0.1)  # Árnyék eltolásának beállítása
    shadow_color = "#000000"  # Árnyékszín beállítása

    for text_info in texts:
        text = text_info["text"]
        font_path = text_info["font"]
        max_height = text_info["max_height"]
        max_size = text_info["size"]
        text_color = text_info["color"]
        position = text_info["position"]
        max_width = text_info.get("max_width")
        line_spacing = text_info.get("line_spacing", 0)
        font_size = calculate_font_size(font_path, max_size, max_width, max_height, text, line_spacing)
        lines, _ = wrap_text(text, font_path, max_width, max_height, font_size, line_spacing)
        y = position[1]

        for line, font_size in lines:
            try:
                font = ImageFont.truetype(font_path, font_size)
            except IOError:
                print(f"Hiba: A {font_path} betűtípusfájl nem található.")
                font = ImageFont.load_default()

            line_width = font.getbbox(line)[2]
            line_height = font.getbbox(line)[3] - font.getbbox(line)[1]
            x = (PRESET_BANNER_WIDTH - line_width) // 2

            # Először az árnyékot rajzolja, majd a kontúrt és a szöveget
            if text == book_title:
                # Árnyék hozzáadása
                draw_text_with_shadow(draw, line, (x, y), font, text_color, shadow_color, shadow_offset, PRESET_TEXTSHADOW_BLUR)
                # Kontúr és szöveg hozzáadása
                draw_text_with_outline(draw, line, (x, y), font, text_color, PRESET_TEXT_OUTLINE_WIDTH)
            else:
                draw_text_with_shadow(draw, line, (x, y), font, text_color, shadow_color, shadow_offset, PRESET_TEXTSHADOW_BLUR)

            y += line_height + line_spacing

    return image

def draw_text_with_shadow(draw, text, position, font, text_color, shadow_color, shadow_offset, shadow_blur_radius):
    x, y = position
    shadow_position = (x + shadow_offset[0], y + shadow_offset[1])

    # Árnyék kép létrehozása
    shadow_image = Image.new('RGBA', draw.im.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow_image)

    # Árnyékszín RGBA formátumra konvertálása az opacitással
    shadow_rgba = hex_to_rgba(shadow_color) + (int(255 * PRESET_TEXTSHADOW_OPACITY / 100),)

    # Árnyék rajzolása az átmeneti képre
    shadow_draw.text(shadow_position, text, font=font, fill=shadow_rgba)

    # Az árnyék elmosása
    shadow_image = shadow_image.filter(ImageFilter.GaussianBlur(shadow_blur_radius))

    # Az árnyék kép összefésülése az eredeti képpel
    draw.bitmap((0, 0), shadow_image, fill=shadow_rgba)

    # Szöveg rajzolása
    draw.text(position, text, font=font, fill=text_color)

def wrap_text(text, font_path, max_width, max_height, font_size, line_spacing):
    font = ImageFont.truetype(font_path, font_size)
    words = text.split()
    lines = []
    current_line = ''
    total_height = 0

    for word in words:
        test_line = current_line + word + ' '
        line_width, line_height = font.getbbox(test_line)[2:4]
        if current_line and line_width > max_width:
            lines.append((current_line, font_size))
            current_line = word + ' '
            total_height += line_height + line_spacing
        else:
            current_line = test_line

    if current_line:
        lines.append((current_line, font_size))
        total_height += line_height + line_spacing

    return lines, total_height

def tint_image(image, color):
    # Tint the image with the given color
    tinted_image = Image.new('RGBA', image.size)
    draw = ImageDraw.Draw(tinted_image)

    for x in range(image.width):
        for y in range(image.height):
            r, g, b, a = image.getpixel((x, y))
            draw.point((x, y), fill=(color[0], color[1], color[2], a))

    return tinted_image

def add_logo(image, logo_path, color_code, right_offset=35, bottom_offset=37):
    logo = Image.open(logo_path).convert("RGBA")

    image_width, image_height = image.size
    logo_width, logo_height = logo.size

    # Calculate the position for the logo, with the specified offsets from the right and bottom edges
    position = (image_width - logo_width - right_offset, image_height - logo_height - bottom_offset)

    image.paste(logo, position, logo)
    return image


# Fő program indítása
def main(input_file_path, output_directory, author_name, book_title, subtitle, font_path, logo_path, color_code):
    preset_texts = get_preset_texts(author_name, book_title, subtitle, font_path, color_code)

    configurations = [
        {
            "background": input_file_path,
            "cover": input_file_path,
            "output": "1080x1920output-1.png"
        }
    ]

    for config in configurations:
        replace_book_cover(config["background"], config["cover"], config["output"], preset_texts, output_directory, logo_path, color_code, book_title)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Könyvborító kép generálása.')
    parser.add_argument('input_file_path', help='Az eredeti kép elérési útja')
    parser.add_argument('output_directory', help='A kimeneti könyvtár elérési útja')
    parser.add_argument('author_name', help='A szerző neve')
    parser.add_argument('book_title', help='A könyv címe')
    parser.add_argument('subtitle', help='A könyv alcíme')
    parser.add_argument('font_path', help='A betűtípus elérési útja')
    parser.add_argument('logo_path', help='A logó képének útvonala.')
    parser.add_argument('color_code', help='A szövegek színe hexadecimális kódban')

    args = parser.parse_args()

    # Létrehozzuk a kimeneti könyvtárat, ha még nem létezik
    if not os.path.exists(args.output_directory):
        os.makedirs(args.output_directory)

    # A fő program elindítása az új argumentumokkal
    main(args.input_file_path, args.output_directory, args.author_name, args.book_title, args.subtitle, args.font_path, args.logo_path, args.color_code)