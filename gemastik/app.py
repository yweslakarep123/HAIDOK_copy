from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.urls import url_parse
from models import db, User, Diagnosis
from config import Config
from google import genai
import json

app = Flask(__name__)
app.config.from_object(Config)

# Inisialisasi database
db.init_app(app)

# Inisialisasi login manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Inisialisasi Gemini
client = genai.Client(api_key=app.config['GEMINI_API_KEY'])

@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))

def format_diagnosis(response_text):
    """Format diagnosis menjadi HTML yang rapi"""
    if "DIAGNOSIS:" not in response_text:
        return response_text
        
    parts = response_text.split('\n')
    formatted_html = '<div class="diagnosis-result">'
    
    for part in parts:
        part = part.strip()
        if not part:
            continue
            
        if part.startswith('DIAGNOSIS:'):
            formatted_html += f'<h5 class="text-primary mb-3">{part}</h5>'
        elif part.startswith('GEJALA YANG MENDASARI:'):
            formatted_html += '<h6 class="mt-3 mb-2">Gejala yang Mendasari:</h6>'
        elif part.startswith('SARAN PENGOBATAN:'):
            formatted_html += '<h6 class="mt-3 mb-2">Saran Pengobatan:</h6>'
        elif part.startswith('1. Obat-obatan:'):
            formatted_html += '<h6 class="mt-2 mb-2">Obat-obatan:</h6>'
        elif part.startswith('2. Perawatan Tambahan:'):
            formatted_html += '<h6 class="mt-2 mb-2">Perawatan Tambahan:</h6>'
        elif part.startswith('3. Pencegahan:'):
            formatted_html += '<h6 class="mt-2 mb-2">Pencegahan:</h6>'
        elif part.startswith('4. Kapan Harus Ke Dokter:'):
            formatted_html += '<h6 class="mt-2 mb-2">Kapan Harus Ke Dokter:</h6>'
        elif part.startswith('- '):
            formatted_html += f'<p class="mb-1"><i class="fas fa-check-circle text-success me-2"></i>{part[2:]}</p>'
        else:
            formatted_html += f'<p class="mb-1">{part}</p>'
    
    formatted_html += '</div>'
    return formatted_html

def get_next_question(user_input, conversation_history):
    prompt = f"""Anda adalah seorang dokter spesialis yang sangat berpengalaman dalam mendiagnosis penyakit.
    Tugas Anda adalah mendiagnosis penyakit pasien dengan sangat teliti dan akurat.
    
    Panduan diagnosis:
    1. Ajukan pertanyaan yang spesifik dan terarah
    2. Perhatikan gejala-gejala yang saling berhubungan
    3. Pertimbangkan faktor risiko dan riwayat kesehatan
    4. Pastikan diagnosis berdasarkan bukti-bukti yang cukup
    
    Riwayat percakapan:
    {conversation_history}
    
    Keluhan terakhir pasien: {user_input}
    
    Berikan respons dalam format:
    Jika masih perlu informasi: Hanya satu pertanyaan lanjutan yang paling relevan
    Jika sudah cukup yakin: 
    DIAGNOSIS: [nama penyakit yang spesifik]
    
    GEJALA YANG MENDASARI:
    - [gejala 1]
    - [gejala 2]
    - [gejala 3]
    
    SARAN PENGOBATAN:
    1. Obat-obatan:
       - [nama obat 1] - [dosis] - [cara konsumsi]
       - [nama obat 2] - [dosis] - [cara konsumsi]
    
    2. Perawatan Tambahan:
       - [saran perawatan 1]
       - [saran perawatan 2]
    
    3. Pencegahan:
       - [saran pencegahan 1]
       - [saran pencegahan 2]
    
    4. Kapan Harus Ke Dokter:
       - [kondisi 1]
       - [kondisi 2]
    """
    
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt
    )
    return response.text

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        if User.query.filter_by(username=username).first():
            flash('Username sudah digunakan')
            return redirect(url_for('register'))
            
        if User.query.filter_by(email=email).first():
            flash('Email sudah digunakan')
            return redirect(url_for('register'))
            
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        flash('Registrasi berhasil! Silakan login.')
        return redirect(url_for('login'))
        
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        
        if user is None or not user.check_password(password):
            flash('Username atau password salah')
            return redirect(url_for('login'))
            
        login_user(user)
        next_page = request.args.get('next')
        if not next_page or url_parse(next_page).netloc != '':
            next_page = url_for('dashboard')
        return redirect(next_page)
        
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    diagnoses = current_user.diagnoses.order_by(Diagnosis.created_at.desc()).all()
    return render_template('dashboard.html', diagnoses=diagnoses)

@app.route('/diagnosis', methods=['GET', 'POST'])
@login_required
def diagnosis():
    if request.method == 'POST':
        data = request.get_json()
        user_input = data.get('message')
        conversation_history = data.get('history', '')
        
        response = get_next_question(user_input, conversation_history)
        formatted_response = format_diagnosis(response)
        
        if "DIAGNOSIS:" in response:
            # Simpan diagnosis ke database
            diagnosis = Diagnosis(
                user_id=current_user.id,
                symptoms=user_input,
                diagnosis=formatted_response,
                treatment=formatted_response,
                conversation_history=conversation_history
            )
            db.session.add(diagnosis)
            db.session.commit()
        
        return jsonify({'response': formatted_response})
        
    return render_template('diagnosis.html')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True) 