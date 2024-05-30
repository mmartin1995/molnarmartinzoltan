from PIL import Image
import os

def convert_image_to_webp(input_path, output_path, target_size_kb=100):
    # Kép megnyitása
    with Image.open(input_path) as img:
        original_size_kb = os.path.getsize(input_path) / 1024  # KB-ban

        # Ha az eredeti méret kisebb, mint a cél méret, konvertálás minőségveszteség nélkül
        if original_size_kb <= target_size_kb:
            img.save(output_path, 'WEBP')
        else:
            # Minőség beállítása és méretcsökkentési próbálkozás, ha a kép mérete nagyobb, mint a cél méret
            quality = 95
            while quality > 0:
                img.save(output_path, 'WEBP', quality=quality)
                output_size_kb = os.path.getsize(output_path) / 1024

                if output_size_kb <= target_size_kb:
                    break  # A cél méret elérve, kilépés a ciklusból

                quality -= 5  # Csökkentjük a minőséget, ha a fájl mérete még mindig túl nagy

def convert_images_to_webp(input_folder, output_folder, max_size_kb=100):
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    for filename in os.listdir(input_folder):
        if filename.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
            input_path = os.path.join(input_folder, filename)
            
            # Ha a fájl már .webp formátumú, akkor ne változtassuk meg a kiterjesztést
            if filename.lower().endswith('.webp'):
                output_path = os.path.join(output_folder, filename)
            else:
                output_path = os.path.join(output_folder, os.path.splitext(filename)[0] + '.webp')

            convert_image_to_webp(input_path, output_path, target_size_kb=max_size_kb)

if __name__ == "__main__":
    convert_images_to_webp("input", "output")