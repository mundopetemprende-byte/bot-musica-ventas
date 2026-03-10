import os
import json
import sqlite3
import requests
from flask import Flask, request, jsonify
from google import genai
from google.genai import types

app = Flask(__name__)

# ===================== CONFIGURACIÓN =====================
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
WHATSAPP_TOKEN = os.getenv('WHATSAPP_ACCESS_TOKEN')
PHONE_NUMBER_ID = os.getenv('WHATSAPP_PHONE_NUMBER_ID')
VERIFY_TOKEN = os.getenv('WHATSAPP_VERIFY_TOKEN')

# Nuevo cliente del SDK 2026
client = genai.Client(api_key=GEMINI_API_KEY)
MODEL_ID = "gemini-2.5-flash"

SYSTEM_INSTRUCTION = """
Eres "Luna", una asistente de ventas colombiana 🇨🇴 para una tienda de canciones personalizadas.
Tu objetivo es ser BREVE, amable y natural. 

REGLAS DE ORO:
1. Jamás mandes más de 2 párrafos cortos.
2. No des precios ni pidas todos los datos en el primer mensaje.
3. Primero saluda y pregunta para quién es la canción o qué ocasión celebran.
4. Usa emojis pero no exageres.
5. Usa expresiones colombianas sutiles (ej: "¡Hola!", "Claro que sí", "Con gusto").

FLUJO DE VENTA:
- Paso 1: Saludo corto y pregunta por el motivo (cumpleaños, aniversario, etc).
- Paso 2: Según lo que digan, ofrece los 2 paquetes (40k normal / 70k con video) de forma sencilla.
- Paso 3: Pide los datos uno por uno (Nombre, género musical, historia).

Si el cliente confirma el pago, responde EXACTAMENTE: "¡Genial! Gracias por tu pago 🎵 En breve te contactamos con tu canción personalizada. ¡Que la disfrutes mucho!" y añade [COMPLETADA] al final.
"""

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
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "text",
        "text": {"body": text}
    }
    response = requests.post(url, json=payload, headers=headers)
    
    # ESTO ES LO QUE NECESITAMOS VER EN LOS LOGS DE RAILWAY
    print(f"--- INTENTO DE ENVÍO A WHATSAPP ---")
    print(f"Estado Meta: {response.status_code}")
    print(f"Respuesta Meta: {response.text}")
    print(f"-----------------------------------")
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
        val = data['entry'][0]['changes'][0]['value']
        if 'messages' not in val: return jsonify(success=True)
            
        message = val['messages'][0]
        phone = message['from']
        user_text = message['text']['body']
        
        row = manage_db("SELECT history, completed FROM chats WHERE phone=?", (phone,), fetch=True)
        history_raw, completed = (json.loads(row[0]), bool(row[1])) if row else ([], False)
        
        if completed:
            send_whatsapp(phone, "¡Tu canción ya está en proceso! 🎵")
            return jsonify(success=True)

        # 1. Convertir historial al nuevo formato de Content types
        chat_history = []
        for h in history_raw:
            chat_history.append(types.Content(role=h['role'], parts=[types.Part(text=h['parts'][0]['text'])]))

        # 2. Generar respuesta con el nuevo SDK
       response = client.models.generate_content(
            model=MODEL_ID,
            contents=chat_history + [types.Content(role="user", parts=[types.Part(text=user_text)])],
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0.8,    # <-- MÁS ALTO = Más creativa y humana
                top_p=0.95,         # <-- Ayuda a que el lenguaje sea fluido
                max_output_tokens=150 # <-- LIMITA la respuesta para que no escriba testamentos
        
        
        
        # 3. Lógica de cierre
        new_completed = 1 if "[COMPLETADA]" in bot_reply else 0
        bot_reply = bot_reply.replace("[COMPLETADA]", "").strip()
        
        send_whatsapp(phone, bot_reply)
        
        # 4. Actualizar historial para la DB
        history_raw.append({"role": "user", "parts": [{"text": user_text}]})
        history_raw.append({"role": "model", "parts": [{"text": bot_reply}]})
        
        manage_db("INSERT OR REPLACE INTO chats VALUES (?, ?, ?)", 
                  (phone, json.dumps(history_raw), new_completed))

    except Exception as e:
        print(f"❌ Error Raíz: {e}")
    
    return jsonify(success=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
