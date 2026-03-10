import os
import json
import sqlite3
import requests
from flask import Flask, request, jsonify
import google.generativeai as genai

app = Flask(__name__)

# ===================== CONFIGURACIÓN =====================
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
WHATSAPP_TOKEN = os.getenv('WHATSAPP_ACCESS_TOKEN')
PHONE_NUMBER_ID = os.getenv('WHATSAPP_PHONE_NUMBER_ID')
VERIFY_TOKEN = os.getenv('WHATSAPP_VERIFY_TOKEN')

genai.configure(api_key=GEMINI_API_KEY)

SYSTEM_INSTRUCTION = """
Eres una asistente de ventas súper amable y natural llamada "Luna" de canciones personalizadas.
Precios: 40.000 COP (normal), 70.000 COP (con video).
Pide: nombre del destinatario, quién la envía, género musical y detalles para la letra.
Responde en español colombiano con emojis. 🇨🇴
Si el cliente confirma el pago, responde EXACTAMENTE: "¡Genial! Gracias por tu pago 🎵 En breve te contactamos con tu canción personalizada. ¡Que la disfrutes mucho!" y añade [COMPLETADA] al final.
"""

# Usamos el modelo que tus logs confirmaron como activo
model = genai.GenerativeModel(
    model_name="gemini-2.5-flash",
    system_instruction=SYSTEM_INSTRUCTION
)

# ===================== BASE DE DATOS =====================
def manage_db(query, params=(), fetch=False):
    conn = sqlite3.connect('conversations.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS chats 
                    (phone TEXT PRIMARY KEY, history TEXT, completed INTEGER DEFAULT 0)''')
    cursor.execute(query, params)
    result = cursor.fetchone() if fetch else None
    conn.commit()
    conn.close()
    return result

# ===================== WHATSAPP =====================
def send_whatsapp(to_phone, text):
    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "text",
        "text": {"body": text}
    }
    requests.post(url, json=payload, headers=headers)

# ===================== WEBHOOK =====================
@app.route('/webhook', methods=['GET'])
def verify():
    if request.args.get('hub.verify_token') == VERIFY_TOKEN:
        return request.args.get('hub.challenge')
    return "Token inválido", 403

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    try:
        if 'messages' not in data['entry'][0]['changes'][0]['value']:
            return jsonify(success=True)
            
        message = data['entry'][0]['changes'][0]['value']['messages'][0]
        phone = message['from']
        user_text = message['text']['body']
        
        # 1. Obtener historial
        row = manage_db("SELECT history, completed FROM chats WHERE phone=?", (phone,), fetch=True)
        history, completed = (json.loads(row[0]), bool(row[1])) if row else ([], False)
        
        if completed:
            send_whatsapp(phone, "¡Tu canción ya está en proceso! 🎵")
            return jsonify(success=True)

        # 2. Llamada a Gemini (SIN RequestOptions para evitar el error de argumento)
        chat = model.start_chat(history=history)
        response = chat.send_message(user_text)
        bot_reply = response.text
        
        # 3. Lógica de cierre
        new_completed = 0
        if "[COMPLETADA]" in bot_reply:
            bot_reply = bot_reply.replace("[COMPLETADA]", "").strip()
            new_completed = 1
        
        send_whatsapp(phone, bot_reply)
        
        # 4. Guardar historial formateado
        new_history = []
        for content in chat.history:
            new_history.append({
                "role": content.role,
                "parts": [{"text": p.text} for p in content.parts]
            })
        
        manage_db("INSERT OR REPLACE INTO chats VALUES (?, ?, ?)", 
                  (phone, json.dumps(new_history), new_completed))

    except Exception as e:
        print(f"❌ Error en el proceso: {e}")
    
    return jsonify(success=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
