from flask import Blueprint, render_template, request, redirect, url_for
import os
import csv

keywordmaker_blueprint = Blueprint('keywordmaker', __name__)

@keywordmaker_blueprint.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # Fájl feltöltése
        file = request.files['file']
        
        if file:
            # Például CSV fájl feldolgozása
            filename = os.path.join('uploads', file.filename)
            file.save(filename)
            
            # Fájl feldolgozása itt
            # Az adatokat kinyerheted és tovább használhatod
            with open(filename, 'r') as f:
                reader = csv.reader(f)
                rows = list(reader)
            
            # Fájl feldolgozása után redirect a sikeres oldala
            return redirect(url_for('keywordmaker.index'))
    
    return render_template('keywordmaker.html')  # A HTML fájl itt található
