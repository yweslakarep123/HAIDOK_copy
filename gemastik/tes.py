from google import genai
import time

def initialize_gemini():
    client = genai.Client(api_key="AIzaSyAIDTlU-u8lfCS3nsXjlEtLKT8wBnn8CGM")
    return client

def get_next_question(client, user_input, conversation_history):
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
       "DIAGNOSIS: [nama penyakit yang spesifik]
       GEJALA YANG MENDASARI:
       - [daftar gejala yang mendukung diagnosis]
       
       SARAN PENGOBATAN:
       1. Obat-obatan:
          - [nama obat spesifik] [dosis] [cara konsumsi]
          - [nama obat spesifik] [dosis] [cara konsumsi]
       2. Perawatan Tambahan:
          - [saran perawatan spesifik]
       3. Pencegahan:
          - [saran pencegahan]
       4. Kapan Harus Ke Dokter:
          - [kondisi yang mengharuskan konsultasi langsung]"
    """
    
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt
    )
    return response.text

def main():
    client = initialize_gemini()
    conversation_history = []
    
    print("Selamat datang di Chatbot Diagnosis Penyakit!")
    print("Silakan jelaskan keluhan awal Anda secara detail. Ketik 'selesai' untuk mengakhiri percakapan.")
    
    # Pertanyaan awal
    user_input = input("\nAnda: ")
    if user_input.lower() == 'selesai':
        print("\nTerima kasih telah menggunakan layanan kami. Semoga lekas sembuh!")
        return
        
    conversation_history.append(f"Pasien: {user_input}")
    
    while True:
        try:
            response = get_next_question(client, user_input, "\n".join(conversation_history))
            print("\nDokter:", response)
            conversation_history.append(f"Dokter: {response}")
            
            # Jika sudah ada diagnosis, akhiri percakapan
            if "DIAGNOSIS:" in response:
                print("\nCatatan: Diagnosis ini adalah perkiraan awal. Selalu konsultasikan dengan dokter untuk diagnosis dan pengobatan yang tepat.")
                print("\nTerima kasih telah menggunakan layanan kami. Semoga lekas sembuh!")
                break
            
            # Tunggu jawaban user
            user_input = input("\nAnda: ")
            if user_input.lower() == 'selesai':
                print("\nTerima kasih telah menggunakan layanan kami. Semoga lekas sembuh!")
                break
                
            conversation_history.append(f"Pasien: {user_input}")
            
            # Menambahkan delay kecil untuk menghindari rate limiting
            time.sleep(1)
            
        except Exception as e:
            print(f"\nMaaf, terjadi kesalahan: {str(e)}")
            print("Silakan coba lagi.")
            break

if __name__ == "__main__":
    main()