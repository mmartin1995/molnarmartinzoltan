from flask import Flask, request, redirect, url_for, render_template, send_from_directory
import pandas as pd
import os

# Blueprint létrehozása
from flask import Blueprint

matrix_blueprint = Blueprint('matrix', __name__, template_folder='../htmls')

UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'output'

matrix_blueprint.config = {
    'UPLOAD_FOLDER': UPLOAD_FOLDER,
    'OUTPUT_FOLDER': OUTPUT_FOLDER
}

@matrix_blueprint.route('/', methods=['GET', 'POST'])
def upload_and_generate_matrix():
    if request.method == 'POST':
        if 'file' not in request.files:
            return 'No file part'
        file = request.files['file']
        if file.filename == '':
            return 'No selected file'
        if file:
            filename = os.path.join(matrix_blueprint.config['UPLOAD_FOLDER'], file.filename)
            file.save(filename)
            
            # Mátrix generálása
            df = pd.read_excel(filename)
            df = df[df['Mennyiség'] > 0]  # Negatív mennyiségek kizárása

            unique_categories = df['Kategória'].unique()
            matrix_df = pd.DataFrame(0, index=unique_categories, columns=unique_categories)

            for order_id in df['Rendelésazonosító'].unique():
                order_df = df[df['Rendelésazonosító'] == order_id]
                
                # Kategóriák és mennyiségek alapján szimmetrikus frissítés
                for i, row in order_df.iterrows():
                    category = row['Kategória']
                    quantity = row['Mennyiség']
                    categories_in_order = order_df['Kategória'].unique()
                    
                    for related_category in categories_in_order:
                        matrix_df.loc[category, related_category] += quantity
                        matrix_df.loc[related_category, category] += quantity  # Szimmetrikus frissítés

            output_filename = 'Kategória_matrix.xlsx'
            output_path = os.path.join(matrix_blueprint.config['OUTPUT_FOLDER'], output_filename)
            matrix_df.to_excel(output_path)

            return redirect(url_for('matrix.download_file', filename=output_filename))

    return render_template('matrixmaker.html')

@matrix_blueprint.route('/download/<filename>')
def download_file(filename):
    return send_from_directory(matrix_blueprint.config['OUTPUT_FOLDER'], filename, as_attachment=True)

if __name__ == "__main__":
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    if not os.path.exists(OUTPUT_FOLDER):
        os.makedirs(OUTPUT_FOLDER)
    app.run(debug=True)
