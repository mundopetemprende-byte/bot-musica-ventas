import os
import json
import sqlite3
import requests
from flask import Flask, request, jsonify
import google.generativeai as genai
from google.generativeai.types import RequestOptions

app = Flask(__name__)

# ===================== CONFIGURACIÓN REFORZADA =====================
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
WHATSAPP_TOKEN = os.getenv('WHATSAPP_ACCESS_TOKEN')
PHONE_NUMBER_ID = os.getenv('WHATSAPP_PHONE_NUMBER_ID')
VERIFY_TOKEN = os.getenv('WHATSAPP_VERIFY_TOKEN')

# Configuración inicial de Google AI
genai.configure(api_key=GEMINI_API_KEY)

# Instrucciones de Luna (Tu Asistente)
SYSTEM_INSTRUCTION = """
Eres una asistente de ventas súper amable y natural llamada "Luna" de canciones personalizadas.
Precios: 
- Canción normal: 40.000 COP
- Canción + video: 70.000 COP

Tu objetivo es recolectar:
1. ¿A quién va dirigida?
2. ¿De parte de quién?
3. ¿Qué género musical?
4. ¿Qué decir en la letra?

Responde en español colombiano con emojis. 🇨🇴
Si el cliente confirma el pago, responde EXACTAMENTE: 
"¡Genial! Gracias por tu pago 🎵 En breve te contactamos con tu canción personalizada. ¡Que la disfrutes mucho!" 
y añade [COMPLETADA] al final de ese mensaje.
"""

# IMPORTANTE: Usamos gemini-2.5-flash porque tus logs muestran que es el activo en 2026
model = genai.GenerativeModel(
    model_name="gemini-2.5-flash",
    system_instruction=SYSTEM_INSTRUCTION
)

# ===================== BASE DE DATOS (SQLite) =====================
def init_db():
    conn = sqlite3.connect('conversations.db')
    conn.execute('''CREATE TABLE IF NOT EXISTS chats 
                    (phone TEXT PRIMARY KEY, history TEXT, completed INTEGER DEFAULT 0)''')
    conn.commit()
    conn.close()

init_db()

def get_chat_data(phone):
    conn = sqlite3.connect('conversations.db')
    cursor = conn.cursor()
    cursor.execute("SELECT history, completed FROM chats WHERE phone=?", (phone,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return json.loads(row[0]), bool(row[1])
    return [], False

def save_chat_data(phone, history, completed):
    conn = sqlite3.connect('conversations.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO chats (phone, history, completed) VALUES (?, ?, ?)",
                   (phone, json.dumps(history), int(completed)))
    conn.commit()
    conn.close()

# ===================== WHATSAPP API =====================
def send_whatsapp(to_phone, text):
    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "text",
        "text": {"body": text}
    }
    try:
        r = requests.post(url, json=payload, headers=headers)
        if r.status_code != 200:
            print(f"Error WhatsApp: {r.text}")
    except Exception as e:
        print(f"Error enviando mensaje: {e}")

# ===================== WEBHOOK =====================
@app.route('/webhook', methods=['GET'])
def verify_webhook():
    if request.args.get('hub.verify_token') == VERIFY_TOKEN:
        return request.args.get('hub.challenge')
    return "Token inválido", 403

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    try:
        # Extraer datos de WhatsApp
        entry = data['entry'][0]
        change = entry['changes'][0]
        value = change['value']
        
        if 'messages' not in value:
            return jsonify(success=True)

        message = value['messages'][0]
        phone = message['from']
        
        if message.get('type') != 'text':
            send_whatsapp(phone, "Por ahora solo puedo entender texto 😊")
            return jsonify(success=True)
            
        user_text = message['text']['body']
        
        # 1. Cargar historial
        history, completed = get_chat_data(phone)
        
        if completed:
            send_whatsapp(phone, "¡Tu canción ya está en proceso! 🎵 Pronto te hablaremos.")
            return jsonify(success=True)
        
        # 2. Generar respuesta con Gemini 2.5
        chat = model.start_chat(history=history)
        # Forzamos v1 para estabilidad
        response = chat.send_message(user_text, request_options=RequestOptions(api_version='v1'))
        bot_reply = response.text
        
        # 3. Verificar si terminó el pedido
        is_now_completed = False
        if "[COMPLETADA]" in bot_reply:
            bot_reply = bot_reply.replace("[COMPLETADA]", "").strip()
            is_now_completed = True
        
        # 4. Enviar a WhatsApp
        send_whatsapp(phone, bot_reply)
        
        # 5. Guardar historial limpio
        new_history = []
        for content in chat.history:
            new_history.append({
                "role": content.role,
                "parts": [{"text": part.text} for part in content.parts]
            })
            
        save_chat_data(phone, new_history, is_now_completed)
        
    except Exception as e:
        print(f"❌ Error en Webhook: {e}")
    
    return jsonify(success=True)

if __name__ == '__main__':
    # Puerto 8080 para Railway
    app.run(host='0.0.0.0', port=8080)
