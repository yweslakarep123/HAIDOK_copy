import os
from dotenv import load_dotenv
import requests

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-yang-aman'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///diagnosis.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY') or 'AIzaSyAIDTlU-u8lfCS3nsXjlEtLKT8wBnn8CGM'
    GOOGLE_PLACES_API_KEY = os.environ.get('GOOGLE_PLACES_API_KEY') or 'ISI_API_KEY_ANDA_DI_SINI'
    TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN') or 'ISI_TOKEN_BOT_TELEGRAM_ANDA' 

# Konfigurasi FCM
server_key = "ISI_SERVER_KEY_FIREBASE_ANDA"  # Dapatkan dari Firebase Console > Project Settings > Cloud Messaging > Server key
fcm_token = "ISI_TOKEN_FCM_YANG_MUNCUL_DI_CONSOLE_BROWSER"
headers = {
    "Authorization": "key=" + server_key,
    "Content-Type": "application/json"
}
data = {
    "to": fcm_token,
    "notification": {
        "title": "Waktunya Minum Obat",
        "body": "Jangan lupa minum obat sesuai jadwal!",
    }
}
# Kode request ke FCM dipindahkan ke tes.py 