from flask import Blueprint, request, render_template, send_file
import pandas as pd
import os

# Blueprint létrehozása
category_blueprint = Blueprint('category', __name__, template_folder='templates')

@category_blueprint.route('/')
def upload_file():
    return render_template('categorymaker.html')

@category_blueprint.route('/uploader', methods=['POST'])
def uploader():
    if 'file' not in request.files:
        return 'No file part'
    file = request.files['file']
    if file.filename == '':
        return 'No selected file'
    
    # Retrieve column indexes and start row from form
    start_row = int(request.form.get('start_row')) - 1
    genre_column_index = int(request.form.get('genre_column')) - 1
    quantity_column_index = int(request.form.get('quantity_column')) - 1
    value_column_index = int(request.form.get('value_column')) - 1
    
    if file:
        # Read the Excel file without setting a specific header
        df = pd.read_excel(file, header=None, skiprows=start_row)

        # Find the first row where all three columns have data
        for i, row in df.iterrows():
            if pd.notna(row[genre_column_index]) and pd.notna(row[quantity_column_index]) and pd.notna(row[value_column_index]):
                df.columns = df.iloc[i]
                df = df.drop(i).reset_index(drop=True)
                break

        # Extract relevant columns based on indexes
        genre_column_name = df.columns[genre_column_index]
        quantity_column_name = df.columns[quantity_column_index]
        value_column_name = df.columns[value_column_index]

        # Process genres
        df[genre_column_name] = df[genre_column_name].str.split(';')
        df = df.explode(genre_column_name).reset_index(drop=True)
        
        # Remove prefix and trim genre to first part
        df[genre_column_name] = df[genre_column_name].str.replace('Könyv > ', '', regex=False)
        df[genre_column_name] = df[genre_column_name].apply(lambda x: x.split(' > ')[0].strip() if isinstance(x, str) else x)

        # Drop rows where genre is NaN
        df = df[df[genre_column_name].notna()]

        # Summarize by genre
        summary_df = df.groupby(genre_column_name, as_index=False).agg({
            quantity_column_name: 'sum',
            value_column_name: 'sum'
        })

        # Save to a new Excel file
        output_filename = 'processed_data.xlsx'
        summary_df.to_excel(output_filename, index=False)

        # Return the file for download
        return send_file(output_filename, as_attachment=True)
