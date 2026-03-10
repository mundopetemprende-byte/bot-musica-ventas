import os
import json
import sqlite3
import requests
from flask import Flask, request, jsonify
import google.generativeai as genai

app = Flask(__name__)

# ===================== CONFIG =====================
# Asegúrate de tener estas variables en tu entorno (Railway, etc.)
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
WHATSAPP_TOKEN = os.getenv('WHATSAPP_ACCESS_TOKEN')
PHONE_NUMBER_ID = os.getenv('WHATSAPP_PHONE_NUMBER_ID')
VERIFY_TOKEN = os.getenv('WHATSAPP_VERIFY_TOKEN')

genai.configure(api_key=GEMINI_API_KEY)

# Configuración del modelo (Corregido el error de comillas y nombre)
SYSTEM_INSTRUCTION = """
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
# ===================== VERIFICACIÓN DE IA =====================
def verificar_ia():
    try:
        print("🔍 Verificando conexión con Gemini...")
        # Intentamos listar los modelos disponibles
        modelos_disponibles = [m.name for m in genai.list_models() 
                               if 'generateContent' in m.supported_generation_methods]
        
        modelo_buscado = "models/gemini-1.5-flash"
        
        if modelo_buscado in modelos_disponibles:
            print(f"✅ ¡Éxito! El modelo {modelo_buscado} está disponible y listo.")
        else:
            print(f"⚠️ Alerta: El modelo {modelo_buscado} no aparece en tu lista.")
            print(f"Modelos que SÍ puedes usar: {modelos_disponibles}")
            
    except Exception as e:
        print(f"❌ Error crítico de API: {e}")
        print("Revisa si tu GEMINI_API_KEY es correcta y tiene permisos.")

# Ejecutar la verificación al iniciar
verificar_ia()

model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    system_instruction=SYSTEM_INSTRUCTION
)

# ===================== BASE DE DATOS =====================
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
def send_message(to_phone, text):
    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "text",
        "text": {"body": text}
    }
    try:
        requests.post(url, json=payload, headers=headers)
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
        # Extraer datos básicos del mensaje
        entry = data['entry'][0]
        change = entry['changes'][0]
        value = change['value']
        
        if 'messages' not in value:
            return jsonify(success=True)

        message = value['messages'][0]
        phone = message['from']
        msg_type = message.get('type')
        
        if msg_type != 'text':
            send_message(phone, "Por ahora solo respondo por texto 😊 Envía el comprobante como foto o texto y te ayudo.")
            return jsonify(success=True)
        
        user_text = message['text']['body']
        
        # 1. Cargar conversación previa
        history, completed = get_chat_data(phone)
        
        if completed:
            send_message(phone, "¡Ya estamos procesando tu canción personalizada! 🎵 En breve te contactamos.")
            return jsonify(success=True)
        
        # 2. Iniciar chat con historial y generar respuesta
        chat = model.start_chat(history=history)
        response = chat.send_message(user_text)
        bot_reply = response.text
        
        # 3. Lógica de finalización
        is_now_completed = False
        if "[COMPLETADA]" in bot_reply:
            bot_reply = bot_reply.replace("[COMPLETADA]", "").strip()
            is_now_completed = True
        
        # 4. Enviar respuesta al usuario
        send_message(phone, bot_reply)
        
        # 5. Guardar el historial actualizado (chat.history contiene el nuevo mensaje y la respuesta)
        # Convertimos el historial de Gemini a un formato serializable (JSON)
        new_history = []
        for content in chat.history:
            new_history.append({
                "role": content.role,
                "parts": [{"text": part.text} for part in content.parts]
            })
            
        save_chat_data(phone, new_history, is_now_completed)
        
    except Exception as e:
        print(f"Error general: {e}")
    
    return jsonify(success=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
