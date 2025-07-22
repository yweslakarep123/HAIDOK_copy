import os
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from google import genai
from datetime import datetime
import json
import base64
from urllib.parse import urlparse
from models import db, User, Diagnosis
from config import Config
from google import genai
from google.genai import types
import re
import requests
from math import radians, cos, sin, asin, sqrt
from flask_migrate import Migrate
from models import MedicationSchedule, PushSubscription
from datetime import datetime, timedelta
from flask import Blueprint
import json

# Tambah model untuk menyimpan push subscription
from sqlalchemy.dialects.sqlite import JSON as SQLiteJSON

# class PushSubscription(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
#     subscription_info = db.Column(SQLiteJSON, nullable=False)
#     created_at = db.Column(db.DateTime, default=datetime.utcnow)

app = Flask(__name__)
app.config.from_object(Config)

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# Inisialisasi database
db.init_app(app)
migrate = Migrate(app, db)

# Inisialisasi login manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Inisialisasi Gemini Client yang benar
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

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash-exp",  # Updated model name
            contents=prompt
        )
        return response.text
    except Exception as e:
        print(f"Error generating content: {e}")
        return "Maaf, terjadi kesalahan dalam memproses permintaan Anda. Silakan coba lagi."


def format_and_translate_response(response_text):
    import re
    text = response_text.strip()
    # Ganti *teks* atau **teks** dengan <b>teks</b>
    text = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', text)  # **bold**
    text = re.sub(r'\*([^*]+)\*', r'<b>\1</b>', text)        # *bold*
    # Ganti dua atau lebih newline dengan <br><br> (paragraf)
    text = re.sub(r'\n{2,}', '<br><br>', text)
    # Ganti satu newline dengan <br>
    text = re.sub(r'\n', '<br>', text)
    # Hilangkan spasi berlebih di awal/akhir baris
    text = re.sub(r'(^|<br>)[ \t]+', r'\1', text)
    return text


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
        if not next_page or urlparse(next_page).netloc != '':  # Fixed urlparse import
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


@app.route('/diagnose-image', methods=['POST'])
@login_required
def diagnose_image():
    if 'image' not in request.files:
        flash('Tidak ada file gambar yang diupload')
        return redirect(url_for('diagnosis'))

    file = request.files['image']
    if file.filename == '':
        flash('Tidak ada file yang dipilih')
        return redirect(url_for('diagnosis'))

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        try:
            # Baca file gambar
            with open(filepath, 'rb') as img_file:
                img_bytes = img_file.read()

            # Menggunakan client yang sudah diinisialisasi dengan benar
            prompt = "Gambar ini adalah foto penyakit atau kondisi kesehatan. Tolong analisa dan sebutkan kemungkinan penyakit atau diagnosisnya secara singkat dan jelas."

            # Buat konten dengan gambar
            image_content = types.Content(
                parts=[
                    types.Part(text=prompt),
                    types.Part(
                        inline_data=types.Blob(
                            mime_type="image/jpeg",  # Sesuaikan dengan tipe file
                            data=img_bytes
                        )
                    )
                ]
            )

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[image_content]
            )

            diagnosis = response.text

            # Hapus file temporary setelah diproses
            os.remove(filepath)

            return render_template('diagnosis.html', diagnosis=diagnosis)

        except Exception as e:
            print(f"Error processing image: {e}")
            flash('Terjadi kesalahan saat memproses gambar')
            if os.path.exists(filepath):
                os.remove(filepath)
            return redirect(url_for('diagnosis'))
    else:
        flash('File tidak diizinkan. Hanya png, jpg, jpeg yang diperbolehkan.')
        return redirect(url_for('diagnosis'))


@app.route('/chat', methods=['POST'])
@login_required
def chat():
    user_message = request.form.get('message', '')
    image_file = request.files.get('image')
    conversation_history = request.form.get('history', '')
    history_id = request.form.get('history_id', '')  # ID diagnosis yang sedang dilanjutkan
    current_diagnosis_id = request.form.get('current_diagnosis_id', '')  # ID diagnosis saat ini
    
    # Debug logging
    print(f"=== CHAT REQUEST ===")
    print(f"User message: {user_message}")
    print(f"Conversation history length: {len(conversation_history)}")
    print(f"History ID: {history_id}")
    print(f"Current diagnosis ID: {current_diagnosis_id}")
    print(f"Has image: {image_file is not None}")
    print(f"Conversation history: {conversation_history}")
    print(f"===================")
    
    # Buat prompt yang memastikan respons dalam Bahasa Indonesia
    base_prompt = "Berikan respons dalam Bahasa Indonesia yang jelas dan mudah dipahami. "
    
    # Jika ada gambar dan ini adalah awal percakapan
    if image_file and image_file.filename != '' and not conversation_history:
        prompt = base_prompt + """Anda adalah seorang dokter yang sedang melakukan pemeriksaan pasien. 

Pasien telah mengirimkan gambar yang menunjukkan kondisi kesehatannya. 

Langkah-langkah yang harus Anda lakukan:
1. Analisa gambar ini dengan teliti
2. Jelaskan apa yang Anda lihat dalam gambar
3. Ajukan SATU pertanyaan lanjutan yang paling relevan untuk memahami kondisi pasien lebih baik

JANGAN langsung memberikan diagnosis atau menebak penyakit. Fokus pada SATU pertanyaan yang paling penting untuk ditanyakan terlebih dahulu.

Contoh pertanyaan yang bisa diajukan:
- "Berapa lama kondisi ini sudah Anda alami?"
- "Apakah ada gejala lain yang menyertai?"
- "Apakah kondisi ini terasa sakit atau gatal?"
- "Apakah ada riwayat penyakit serupa sebelumnya?"

Pilih pertanyaan yang paling relevan berdasarkan apa yang terlihat dalam gambar."""
    
    # Jika ada gambar dan sudah ada riwayat percakapan
    elif image_file and image_file.filename != '' and conversation_history:
        prompt = base_prompt + f"""Anda adalah seorang dokter yang sedang melakukan pemeriksaan pasien.

Riwayat percakapan sebelumnya:
{conversation_history}

Pasien telah mengirimkan gambar dan memberikan jawaban atas pertanyaan Anda. 

Berdasarkan gambar dan jawaban pasien, lanjutkan dengan:
1. Analisa jawaban pasien
2. Ajukan SATU pertanyaan lanjutan yang paling relevan
3. Jika sudah cukup informasi, berikan diagnosis dan saran pengobatan

JANGAN memberikan semua pertanyaan sekaligus. Ajukan SATU pertanyaan yang paling penting untuk tahap ini."""
    
    # Jika hanya teks (lanjutan percakapan)
    elif user_message and conversation_history:
        prompt = base_prompt + f"""Anda adalah seorang dokter yang sedang melakukan pemeriksaan pasien.

Riwayat percakapan sebelumnya:
{conversation_history}

Pasien baru saja menjawab: "{user_message}"

Berdasarkan jawaban pasien ini, lanjutkan dengan:
1. Analisa jawaban pasien
2. Ajukan SATU pertanyaan lanjutan yang paling relevan
3. Jika sudah cukup informasi, berikan diagnosis dan saran pengobatan

JANGAN memberikan semua pertanyaan sekaligus. Ajukan SATU pertanyaan yang paling penting untuk tahap ini."""
    
    # Jika hanya teks tanpa riwayat (keluhan pertama kali)
    elif user_message and not conversation_history:
        prompt = base_prompt + f"""Anda adalah seorang dokter yang sedang melakukan pemeriksaan pasien.

Pasien baru saja mengeluhkan: "{user_message}"

Langkah-langkah yang harus Anda lakukan:
1. Analisa keluhan pasien dengan teliti
2. Ajukan SATU pertanyaan lanjutan yang paling relevan untuk memahami kondisi pasien lebih baik

JANGAN langsung memberikan diagnosis atau menebak penyakit. Fokus pada SATU pertanyaan yang paling penting untuk ditanyakan terlebih dahulu.

Contoh pertanyaan yang bisa diajukan berdasarkan keluhan:
- Jika keluhan sakit kepala: "Di bagian mana tepatnya kepala Anda terasa sakit?"
- Jika keluhan demam: "Berapa suhu tubuh Anda saat ini?"
- Jika keluhan mual: "Apakah disertai dengan muntah?"
- Jika keluhan lemas: "Sejak kapan Anda merasakan gejala ini?"

Pilih pertanyaan yang paling relevan berdasarkan keluhan yang disampaikan pasien."""
    
    # Jika tidak ada input sama sekali
    else:
        prompt = base_prompt + "Berikan saran kesehatan umum dalam Bahasa Indonesia."
    
    try:
        # Siapkan konten untuk Gemini
        parts = []
        parts.append(types.Part(text=prompt))
        
        if image_file and image_file.filename != '':
            img_bytes = image_file.read()
            mime_type = image_file.mimetype or 'image/jpeg'
            parts.append(
                types.Part(
                    inline_data=types.Blob(
                        mime_type=mime_type,
                        data=img_bytes
                    )
                )
            )
        
        image_content = types.Content(parts=parts)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[image_content]
        )
        
        # Pastikan respons dalam Bahasa Indonesia
        diagnosis = ensure_indonesian_response(response.text)
        
        # Buat riwayat lengkap untuk disimpan
        current_interaction = f"Pasien: {user_message if user_message else 'Upload gambar'}\nDokter: {diagnosis}"
        full_conversation = conversation_history + "\n" + current_interaction if conversation_history else current_interaction
        
        # Deteksi apakah ini adalah diagnosis final (bukan pertanyaan lanjutan)
        diagnosis_keywords = ['diagnosis', 'diagnosa', 'kesimpulan', 'berdasarkan', 'kemungkinan', 'penyakit', 'kondisi']
        is_final_diagnosis = any(keyword in diagnosis.lower() for keyword in diagnosis_keywords)
        
        # Tentukan diagnosis record yang akan diupdate
        diagnosis_record = None
        
        # Jika ada current_diagnosis_id (sesi yang sedang berlangsung), gunakan itu
        if current_diagnosis_id:
            diagnosis_record = Diagnosis.query.filter_by(id=current_diagnosis_id, user_id=current_user.id).first()
            print(f"Found existing diagnosis record: {diagnosis_record.id if diagnosis_record else 'None'}")
        # Jika ada history_id (lanjutan percakapan), gunakan itu
        elif history_id:
            diagnosis_record = Diagnosis.query.filter_by(id=history_id, user_id=current_user.id).first()
            print(f"Found history diagnosis record: {diagnosis_record.id if diagnosis_record else 'None'}")
            if not diagnosis_record:
                return jsonify({'error': 'Diagnosis tidak ditemukan'}), 404
        # Jika tidak ada keduanya, buat record baru
        else:
            print("Creating new diagnosis record")
            initial_symptom = user_message if user_message else "Analisis gambar"
            diagnosis_record = Diagnosis(
                user_id=current_user.id,
                symptoms=initial_symptom,
                diagnosis="",  # Kosongkan dulu, akan diisi nanti
                treatment="",
                conversation_history=full_conversation
            )
            db.session.add(diagnosis_record)
            db.session.commit()
            print(f"Created new diagnosis record: {diagnosis_record.id}")
        
        # Return response dengan diagnosis_id untuk disimpan oleh frontend
        return jsonify({
            'response': diagnosis,
            'diagnosis_id': diagnosis_record.id if diagnosis_record else None
        })
    except Exception as e:
        print(f"Error in /chat: {e}")
        return jsonify({'error': 'Terjadi kesalahan saat memproses chat.'}), 500

def ensure_indonesian_response(response_text):
    """Memastikan respons dalam Bahasa Indonesia"""
    # Filter out meta-commentary responses
    unwanted_patterns = [
        "Teks yang Anda berikan sudah dalam Bahasa Indonesia",
        "Berikut adalah terjemahan",
        "Berikut adalah teks tersebut",
        "Tidak ada terjemahan yang diperlukan",
        "yang sebagian besar sama dengan teks asli",
        "perubahannya akan sangat minimal",
        "teks aslinya sudah sangat baik"
    ]
    
    # Cek apakah respons mengandung meta-commentary yang tidak diinginkan
    response_lower = response_text.lower()
    if any(pattern.lower() in response_lower for pattern in unwanted_patterns):
        # Coba ekstrak konten yang sebenarnya
        lines = response_text.split('\n')
        actual_content = []
        skip_mode = False
        
        for line in lines:
            line_lower = line.lower().strip()
            # Skip baris yang mengandung meta-commentary
            if any(pattern.lower() in line_lower for pattern in unwanted_patterns):
                skip_mode = True
                continue
            # Jika menemukan baris yang dimulai dengan "Berikut adalah" atau "Teks yang", skip
            if line_lower.startswith(('berikut adalah', 'teks yang')):
                skip_mode = True
                continue
            # Jika sudah keluar dari mode skip dan menemukan konten yang sebenarnya
            if skip_mode and line.strip() and not line_lower.startswith(('catatan:', 'note:')):
                skip_mode = False
            if not skip_mode and line.strip():
                actual_content.append(line)
        
        # Jika berhasil mengekstrak konten, gunakan itu
        if actual_content:
            response_text = '\n'.join(actual_content)
        else:
            # Jika gagal mengekstrak, coba request ulang dengan prompt yang lebih spesifik
            try:
                clean_prompt = f"""Berikan hanya jawaban atau penjelasan yang diminta, tanpa komentar tentang terjemahan atau format. 

Konten yang perlu diproses:
{response_text}

Berikan hanya jawaban yang sebenarnya dalam Bahasa Indonesia yang baik dan benar."""
                
                clean_response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=types.Content(parts=[types.Part(text=clean_prompt)])
                )
                response_text = clean_response.text
            except:
                # Jika masih gagal, return asli dengan pembersihan minimal
                pass
    
    # Cek apakah respons mengandung kata-kata Bahasa Inggris yang umum
    english_indicators = ['the', 'is', 'are', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by']
    text_lower = response_text.lower()
    
    # Jika terdeteksi Bahasa Inggris, tambahkan instruksi untuk terjemahkan
    if any(indicator in text_lower for indicator in english_indicators):
        # Tambahkan instruksi untuk terjemahkan ke Bahasa Indonesia
        translation_prompt = f"""Terjemahkan ke Bahasa Indonesia yang baik dan benar. Berikan hanya terjemahan tanpa komentar tambahan:

{response_text}"""
        try:
            translation_response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=types.Content(parts=[types.Part(text=translation_prompt)])
            )
            return format_and_translate_response(translation_response.text)
        except:
            # Jika gagal translate, return asli dengan catatan
            return format_and_translate_response(response_text + "\n\n(Catatan: Respons ini mungkin perlu diterjemahkan ke Bahasa Indonesia)")
    
    return format_and_translate_response(response_text)


@app.route('/get-diagnosis-history/<int:diagnosis_id>')
@login_required
def get_diagnosis_history(diagnosis_id):
    """Ambil riwayat diagnosis untuk melanjutkan percakapan"""
    diagnosis = Diagnosis.query.filter_by(id=diagnosis_id, user_id=current_user.id).first()
    if diagnosis:
        return jsonify({
            'conversation_history': diagnosis.conversation_history,
            'diagnosis': diagnosis.diagnosis,
            'symptoms': diagnosis.symptoms,
            'created_at': diagnosis.created_at.strftime('%Y-%m-%d %H:%M:%S')
        })
    return jsonify({'error': 'Diagnosis tidak ditemukan'}), 404

@app.route('/continue-diagnosis', methods=['POST'])
@login_required
def continue_diagnosis():
    """Lanjutkan percakapan dengan diagnosis sebelumnya"""
    data = request.get_json()
    diagnosis_id = data.get('diagnosis_id')
    user_message = data.get('message', '')
    
    # Ambil diagnosis sebelumnya
    diagnosis = Diagnosis.query.filter_by(id=diagnosis_id, user_id=current_user.id).first()
    if not diagnosis:
        return jsonify({'error': 'Diagnosis tidak ditemukan'}), 404
    
    # Buat prompt untuk melanjutkan percakapan
    prompt = f"""Anda adalah seorang dokter yang sedang melanjutkan pemeriksaan pasien.

Riwayat diagnosis sebelumnya:
{diagnosis.conversation_history}

Pasien kembali dengan keluhan: "{user_message}"

Berdasarkan riwayat sebelumnya dan keluhan baru pasien:
1. Analisa apakah gejala masih berlanjut atau ada perubahan
2. Jika diagnosis sebelumnya mungkin salah, tanyakan lebih detail
3. Jika gejala baru muncul, ajukan pertanyaan lanjutan
4. Berikan saran pengobatan yang sesuai

Berikan respons yang membantu dan profesional dalam Bahasa Indonesia."""
    
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=types.Content(parts=[types.Part(text=prompt)])
        )
        
        bot_response = ensure_indonesian_response(response.text)
        
        # Update riwayat percakapan
        updated_conversation = diagnosis.conversation_history + f"\nPasien: {user_message}\nDokter: {bot_response}"
        diagnosis.conversation_history = updated_conversation
        db.session.commit()
        
        return jsonify({'response': bot_response})
    except Exception as e:
        print(f"Error in continue_diagnosis: {e}")
        return jsonify({'error': 'Terjadi kesalahan saat memproses chat.'}), 500

@app.route('/delete-diagnosis/<int:diagnosis_id>', methods=['DELETE'])
@login_required
def delete_diagnosis(diagnosis_id):
    """Hapus riwayat diagnosis"""
    try:
        # Cari diagnosis yang dimiliki user
        diagnosis = Diagnosis.query.filter_by(id=diagnosis_id, user_id=current_user.id).first()
        
        if not diagnosis:
            return jsonify({'success': False, 'error': 'Diagnosis tidak ditemukan'}), 404
        
        # Hapus diagnosis dari database
        db.session.delete(diagnosis)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Riwayat diagnosis berhasil dihapus'})
    except Exception as e:
        print(f"Error deleting diagnosis: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': 'Terjadi kesalahan saat menghapus diagnosis'}), 500

@app.route('/save-conversation', methods=['POST'])
@login_required
def save_conversation():
    """Simpan percakapan ke database setelah model merespons"""
    try:
        data = request.get_json()
        user_message = data.get('user_message', '')
        bot_response = data.get('bot_response', '')
        conversation_history = data.get('conversation_history', '')
        diagnosis_id = data.get('diagnosis_id')
        
        print(f"=== SAVE CONVERSATION REQUEST ===")
        print(f"User message: {user_message}")
        print(f"Bot response: {bot_response}")
        print(f"Diagnosis ID: {diagnosis_id}")
        print(f"Conversation history length: {len(conversation_history)}")
        
        # Tentukan diagnosis record yang akan diupdate
        diagnosis_record = None
        
        if diagnosis_id:
            diagnosis_record = Diagnosis.query.filter_by(id=diagnosis_id, user_id=current_user.id).first()
            print(f"Found diagnosis record: {diagnosis_record.id if diagnosis_record else 'None'}")
        
        if not diagnosis_record:
            print("No diagnosis record found, creating new one")
            # Buat record baru jika tidak ada
            initial_symptom = user_message if user_message else "Percakapan"
            diagnosis_record = Diagnosis(
                user_id=current_user.id,
                symptoms=initial_symptom,
                diagnosis="",
                treatment="",
                conversation_history=conversation_history
            )
            db.session.add(diagnosis_record)
            print(f"Created new diagnosis record: {diagnosis_record.id}")
        else:
            print(f"Updating existing diagnosis record: {diagnosis_record.id}")
            # Update record yang sudah ada
            diagnosis_record.conversation_history = conversation_history
            
            # Deteksi apakah ini diagnosis final
            diagnosis_keywords = ['diagnosis', 'diagnosa', 'kesimpulan', 'berdasarkan', 'kemungkinan', 'penyakit', 'kondisi']
            is_final_diagnosis = any(keyword in bot_response.lower() for keyword in diagnosis_keywords)
            
            if is_final_diagnosis:
                diagnosis_record.diagnosis = bot_response
                diagnosis_record.treatment = bot_response
                print("Updated with final diagnosis")
        
        db.session.commit()
        print(f"Successfully saved conversation to diagnosis record {diagnosis_record.id}")
        
        return jsonify({
            'success': True,
            'diagnosis_id': diagnosis_record.id,
            'message': 'Percakapan berhasil disimpan'
        })
        
    except Exception as e:
        print(f"Error saving conversation: {e}")
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Terjadi kesalahan saat menyimpan percakapan'
        }), 500

# Load drug database
def load_drug_database():
    """Load drug database from CSV file"""
    try:
        df = pd.read_csv('Obat_Bebas dan Bebas_Terbatas - products.csv')
        return df
    except Exception as e:
        print(f"Error loading drug database: {e}")
        return pd.DataFrame()

# Global variable untuk menyimpan database obat
drug_database = load_drug_database()

@app.route('/drug-recommendation')
@login_required
def drug_recommendation():
    """Halaman pencarian obat"""
    return render_template('drug_recommendation.html')

@app.route('/search-drugs', methods=['POST'])
@login_required
def search_drugs():
    """Endpoint untuk mencari obat berdasarkan nama atau gejala"""
    try:
        data = request.get_json()
        query = data.get('query', '').lower()
        
        if not query:
            return jsonify({'error': 'Query pencarian harus diisi'}), 400
        
        print(f"=== DRUG SEARCH REQUEST ===")
        print(f"Query: {query}")
        
        # Filter database berdasarkan query
        filtered_drugs = drug_database[
            drug_database['title'].str.lower().str.contains(query, na=False) |
            drug_database['description'].str.lower().str.contains(query, na=False)
        ]
        
        if filtered_drugs.empty:
            return jsonify({
                'message': 'Tidak ada obat yang ditemukan',
                'drugs': []
            })
        
        # Ambil 10 hasil teratas
        results = filtered_drugs.head(10).to_dict('records')
        
        print(f"Found {len(results)} drugs")
        
        return jsonify({
            'drugs': results,
            'count': len(results)
        })
        
    except Exception as e:
        print(f"Error in drug search: {e}")
        return jsonify({'error': 'Terjadi kesalahan saat mencari obat'}), 500

@app.route('/health-facilities')
@login_required
def health_facilities():
    return render_template('health_facilities.html')

@app.route('/search-health-facilities', methods=['POST'])
@login_required
def search_health_facilities():
    data = request.get_json()
    address = data.get('address', '')
    facility_type = data.get('facility_type', 'all')
    radius_km = float(data.get('radius', 5))

    # Step 1: Geocode address to lat/lon
    nominatim_url = 'https://nominatim.openstreetmap.org/search'
    params = {
        'q': address,
        'format': 'json',
        'limit': 1
    }
    geo_resp = requests.get(nominatim_url, params=params, headers={'User-Agent': 'health-facility-app'})
    geo_data = geo_resp.json()
    if not geo_data:
        return jsonify({'error': 'Lokasi tidak ditemukan'}), 404
    lat = float(geo_data[0]['lat'])
    lon = float(geo_data[0]['lon'])

    # Step 2: Build Overpass QL query
    facility_tags = {
        'all': '(node["amenity"~"pharmacy|clinic|hospital|doctors|health_post"];way["amenity"~"pharmacy|clinic|hospital|doctors|health_post"];);',
        'pharmacy': '(node["amenity"="pharmacy"];way["amenity"="pharmacy"];);',
        'clinic': '(node["amenity"="clinic"];way["amenity"="clinic"];);',
        'hospital': '(node["amenity"="hospital"];way["amenity"="hospital"];);',
        'puskesmas': '(node["amenity"="health_post"];way["amenity"="health_post"];);'
    }
    overpass_query = f"""
    [out:json][timeout:25];
    (
      {facility_tags.get(facility_type, facility_tags['all'])}
    );
    (._;>;);
    out center;
    """
    overpass_url = 'https://overpass-api.de/api/interpreter'
    bbox = f'{lat - radius_km/111.0},{lon - radius_km/111.0},{lat + radius_km/111.0},{lon + radius_km/111.0}'
    overpass_query = f'''[out:json][timeout:25];(node["amenity"~"pharmacy|clinic|hospital|doctors|health_post"]({bbox});way["amenity"~"pharmacy|clinic|hospital|doctors|health_post"]({bbox}););out center;'''
    overpass_resp = requests.post(overpass_url, data={'data': overpass_query})
    overpass_data = overpass_resp.json()
    facilities = []
    for el in overpass_data.get('elements', []):
        tags = el.get('tags', {})
        name = tags.get('name', 'Tanpa Nama')
        amenity = tags.get('amenity', '-')
        address = tags.get('address', '') or tags.get('addr:full', '') or tags.get('addr:street', '') or ''
        phone = tags.get('phone', '-')
        opening_hours = tags.get('opening_hours', '-')
        lat_fac = el.get('lat') or el.get('center', {}).get('lat')
        lon_fac = el.get('lon') or el.get('center', {}).get('lon')
        if not lat_fac or not lon_fac:
            continue
        # Calculate distance
        dist = haversine(lon, lat, float(lon_fac), float(lat_fac))
        # Google Maps link
        gmaps_link = f'https://www.google.com/maps/search/?api=1&query={lat_fac},{lon_fac}'
        facilities.append({
            'name': name,
            'amenity': amenity,
            'address': address,
            'phone': phone,
            'opening_hours': opening_hours,
            'lat': lat_fac,
            'lon': lon_fac,
            'distance': round(dist, 2),
            'gmaps_link': gmaps_link
        })
    facilities = sorted(facilities, key=lambda x: x['distance'])[:20]
    return jsonify({'facilities': facilities})

def haversine(lon1, lat1, lon2, lat2):
    # convert decimal degrees to radians
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    # haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    r = 6371  # Radius of earth in kilometers
    return c * r

@app.route('/medication-schedule')
@login_required
def medication_schedule_page():
    return render_template('medication_schedule.html')

@app.route('/api/medication-schedule', methods=['GET'])
@login_required
def get_medication_schedules():
    schedules = MedicationSchedule.query.filter_by(user_id=current_user.id).order_by(MedicationSchedule.waktu_mulai).all()
    result = []
    for s in schedules:
        result.append({
            'id': s.id,
            'nama_obat': s.nama_obat,
            'interval_jam': s.interval_jam,
            'waktu_mulai': s.waktu_mulai.strftime('%Y-%m-%d %H:%M'),
            'catatan': s.catatan,
            'aktif': s.aktif
        })
    return jsonify(result)

@app.route('/api/medication-schedule', methods=['POST'])
@login_required
def add_medication_schedule():
    data = request.get_json()
    nama_obat = data.get('nama_obat')
    interval_jam = int(data.get('interval_jam'))
    waktu_mulai = datetime.strptime(data.get('waktu_mulai'), '%Y-%m-%dT%H:%M')
    catatan = data.get('catatan', '')
    aktif = data.get('aktif', True)
    schedule = MedicationSchedule(
        user_id=current_user.id,
        nama_obat=nama_obat,
        interval_jam=interval_jam,
        waktu_mulai=waktu_mulai,
        catatan=catatan,
        aktif=aktif
    )
    db.session.add(schedule)
    db.session.commit()
    return jsonify({'success': True, 'id': schedule.id})

@app.route('/api/medication-schedule/<int:schedule_id>', methods=['DELETE'])
@login_required
def delete_medication_schedule(schedule_id):
    schedule = MedicationSchedule.query.filter_by(id=schedule_id, user_id=current_user.id).first()
    if not schedule:
        return jsonify({'error': 'Jadwal tidak ditemukan'}), 404
    db.session.delete(schedule)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/medication-schedule/<int:schedule_id>', methods=['PUT'])
@login_required
def update_medication_schedule(schedule_id):
    schedule = MedicationSchedule.query.filter_by(id=schedule_id, user_id=current_user.id).first()
    if not schedule:
        return jsonify({'error': 'Jadwal tidak ditemukan'}), 404
    data = request.get_json()
    schedule.nama_obat = data.get('nama_obat', schedule.nama_obat)
    schedule.interval_jam = int(data.get('interval_jam', schedule.interval_jam))
    if data.get('waktu_mulai'):
        schedule.waktu_mulai = datetime.strptime(data.get('waktu_mulai'), '%Y-%m-%dT%H:%M')
    schedule.catatan = data.get('catatan', schedule.catatan)
    schedule.aktif = data.get('aktif', schedule.aktif)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/push-subscription', methods=['POST'])
@login_required
def register_push_subscription():
    data = request.get_json()
    # Hapus subscription lama user jika ada
    PushSubscription.query.filter_by(user_id=current_user.id).delete()
    sub = PushSubscription(user_id=current_user.id, subscription_info=data)
    db.session.add(sub)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/static/sw.js')
def service_worker():
    return send_from_directory('static', 'sw.js')


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)