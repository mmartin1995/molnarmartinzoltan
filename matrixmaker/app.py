import pandas as pd

# 1. lépés: Adatok beolvasása
df = pd.read_excel('table.xlsx')

# 2. lépés: Mátrix készítése
# Először hozzunk létre egy üres DataFrame-et a kategóriák számára, 0 értékekkel inicializálva.
unique_categories = df['Kategória'].unique()
# Inicializálás 0 értékekkel
matrix_df = pd.DataFrame(0, index=unique_categories, columns=unique_categories)

# 3. lépés: Azonos rendelésazonosítók alapján számoljuk meg az egyes kategória-kombinációkat
for order_id in df['Rendelésazonosító'].unique():
    categories_in_order = df[df['Rendelésazonosító'] == order_id]['Kategória'].unique()
    for category in categories_in_order:
        # A 'categories_in_order' minden eleméhez hozzáadunk 1-et, kivéve, ha az azonos a sorban lévő kategóriával
        matrix_df.loc[category, categories_in_order] += 1

# 4. lépés: Eredmény exportálása
matrix_df.to_excel('Kategória matrix.xlsx')