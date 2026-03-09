import os
import json
import sqlite3
import requests
from flask import Flask, request, jsonify
import google.generativeai as genai

app = Flask(__name__)

# ===================== CONFIG =====================
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
WHATSAPP_TOKEN = os.getenv('WHATSAPP_ACCESS_TOKEN')
PHONE_NUMBER_ID = os.getenv('WHATSAPP_PHONE_NUMBER_ID')
VERIFY_TOKEN = os.getenv('WHATSAPP_VERIFY_TOKEN')

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    system_instruction="""
Eres una asistente de ventas súper amable y natural llamada "Luna" de canciones personalizadas.
Precios: 
- Canción normal: 40.000 COP
- Canción + video: 70.000 COP

Tu objetivo es recolectar de forma natural:
1. ¿A quién va dirigida la canción? (nombre)
2. ¿De parte de quién?
3. ¿Qué género musical?
4. ¿Qué quieres destacar o decir en la letra?

Sé cálida, usa emojis, responde en español colombiano.
Cuando tengas toda la información, di algo como: "¡Perfecto! ¿Quieres la versión normal por 40.000 o con video por 70.000? Una vez hagas el pago, te la enviamos rapidísimo 💨"

Si el cliente menciona que ya pagó (palabras como pagué, transferí, comprobante, listo, enviado), responde EXACTAMENTE esto y agrega al final [COMPLETADA]:
"¡Genial! Gracias por tu pago 🎵 En breve te contactamos con tu canción personalizada. ¡Que la disfrutes mucho!"

Nunca menciones que eres un bot.
"""
)

# Base de datos SQLite
conn = sqlite3.connect('conversations.db', check_same_thread=False)
conn.execute('''CREATE TABLE IF NOT EXISTS chats 
                (phone TEXT PRIMARY KEY, history TEXT, completed INTEGER DEFAULT 0)''')
conn.commit()

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

def get_or_create_chat(phone):
    cursor = conn.cursor()
    cursor.execute("SELECT history, completed FROM chats WHERE phone=?", (phone,))
    row = cursor.fetchone()
    if row:
        return json.loads(row[0]), bool(row[1])
    return [], False

def save_chat(phone, history, completed):
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO chats VALUES (?, ?, ?)",
                   (phone, json.dumps(history), int(completed)))
    conn.commit()

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
        entry = data['entry'][0]
        change = entry['changes'][0]
        message = change['value']['messages'][0]
        
        phone = message['from']
        msg_type = message.get('type')
        
        if msg_type != 'text':
            send_message(phone, "Por ahora solo respondo por texto 😊 Envía el comprobante como foto o texto y te ayudo.")
            return jsonify(success=True)
        
        user_text = message['text']['body']
        
        # Cargar conversación
        history, completed = get_or_create_chat(phone)
        
        if completed:
            send_message(phone, "¡Ya estamos procesando tu canción personalizada! 🎵 En breve te contactamos.")
            return jsonify(success=True)
        
        # Agregar mensaje del usuario al historial
        history.append({"role": "user", "parts": [{"text": user_text}]})
        
        # Generar respuesta con Gemini
        chat = model.start_chat(history=history)
        response = chat.send_message(user_text)
        bot_reply = response.text
        
        # Verificar si se completó el pago
        if "[COMPLETADA]" in bot_reply:
            bot_reply = bot_reply.replace("[COMPLETADA]", "").strip()
            completed = True
        
        # Enviar respuesta
        send_message(phone, bot_reply)
        
        # Guardar historial y estado
        history.append({"role": "model", "parts": [{"text": bot_reply}]})
        save_chat(phone, history, completed)
        
    except Exception as e:
        print("Error:", e)  # para ver en Railway logs
    
    return jsonify(success=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
