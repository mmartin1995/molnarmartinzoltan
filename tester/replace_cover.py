from PIL import Image

def replace_book_cover(background_path, cover_path, output_path, position=(0, 0), size=(300, 400)):
    # Háttér és borító kép betöltése
    background = Image.open(background_path)
    cover = Image.open(cover_path)

    # A borító méretének átméretezése
    cover = cover.resize(size)

    # A borító beillesztése a háttérképre a megadott pozícióban
    background.paste(cover, position)

    # Eredmény mentése
    background.save(output_path)

# Példa futtatás
replace_book_cover('background.jpg', 'cover.jpg', 'output.jpg', position=(100, 100), size=(300, 400))
