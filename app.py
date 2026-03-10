import os
import json
import sqlite3
import requests
from flask import Flask, request, jsonify
import google.generativeai as genai
from google.generativeai.types import RequestOptions # IMPORTANTE

app = Flask(__name__)

# ===================== CONFIGURACIÓN REFORZADA =====================
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
WHATSAPP_TOKEN = os.getenv('WHATSAPP_ACCESS_TOKEN')
PHONE_NUMBER_ID = os.getenv('WHATSAPP_PHONE_NUMBER_ID')
VERIFY_TOKEN = os.getenv('WHATSAPP_VERIFY_TOKEN')

# 1. Forzamos el uso de la API v1 (la estable) en lugar de v1beta
genai.configure(api_key=GEMINI_API_KEY, transport='rest') 

SYSTEM_INSTRUCTION = """
Eres una asistente de ventas súper amable y natural llamada "Luna" de canciones personalizadas.
Precios: 40.000 COP (normal), 70.000 COP (con video).
Pide: nombre, quién envía, género musical y detalles de la letra.
Responde en español colombiano con emojis. 🇨🇴
"""

# 2. Definimos el modelo sin el prefijo 'models/' para que el SDK lo maneje solo
# Y añadimos RequestOptions para asegurar la versión de la API
model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    system_instruction=SYSTEM_INSTRUCTION
)

# FUNCIÓN DE DIAGNÓSTICO (Aparecerá en tus logs de Railway)
def chequear_modelos():
    print("--- INICIANDO DIAGNÓSTICO DE MODELOS ---")
    try:
        for m in genai.list_models():
            print(f"Modelo disponible: {m.name}")
    except Exception as e:
        print(f"Error listando modelos: {e}")
    print("---------------------------------------")

chequear_modelos()

# ===================== RESTO DEL CÓDIGO (DB y WEBHOOK) =====================
# (Aquí sigue igual que el anterior, pero asegúrate de usar 'model' como está arriba)

def send_message(to_phone, text):
    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "text",
        "text": {"body": text}
    }
    requests.post(url, json=payload, headers=headers)

def get_chat_data(phone):
    conn = sqlite3.connect('conversations.db')
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS chats (phone TEXT PRIMARY KEY, history TEXT, completed INTEGER DEFAULT 0)")
    cursor.execute("SELECT history, completed FROM chats WHERE phone=?", (phone,))
    row = cursor.fetchone()
    conn.close()
    if row: return json.loads(row[0]), bool(row[1])
    return [], False

def save_chat_data(phone, history, completed):
    conn = sqlite3.connect('conversations.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO chats VALUES (?, ?, ?)", (phone, json.dumps(history), int(completed)))
    conn.commit()
    conn.close()

@app.route('/webhook', methods=['GET'])
def verify_webhook():
    if request.args.get('hub.verify_token') == VERIFY_TOKEN:
        return request.args.get('hub.challenge')
    return "Token inválido", 403

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    try:
        msg_data = data['entry'][0]['changes'][0]['value']['messages'][0]
        phone = msg_data['from']
        user_text = msg_data['text']['body']
        
        history, completed = get_chat_data(phone)
        if completed:
            send_message(phone, "¡Ya estamos procesando tu canción! 🎵")
            return jsonify(success=True)

        # Usamos RequestOptions para forzar la API estable si el 404 persiste
        chat = model.start_chat(history=history)
        response = chat.send_message(user_text, request_options=RequestOptions(api_version='v1'))
        
        bot_reply = response.text
        is_completed = "[COMPLETADA]" in bot_reply
        bot_reply = bot_reply.replace("[COMPLETADA]", "").strip()

        send_message(phone, bot_reply)
        
        # Guardar historial limpio
        serializable_history = []
        for content in chat.history:
            serializable_history.append({
                "role": content.role,
                "parts": [{"text": part.text} for part in content.parts]
            })
        save_chat_data(phone, serializable_history, is_completed)

    except Exception as e:
        print(f"Error detallado: {e}")
    
    return jsonify(success=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
