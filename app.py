import os
import requests
from flask import Flask, request
from google import genai
from google.genai import types

app = Flask(__name__)

# --- CONFIGURACIÓN DE VARIABLES (RAILWAY) ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")

# Configuración del Cliente Gemini 2026
client = genai.Client(api_key=GEMINI_API_KEY)
MODEL_ID = "gemini-2.0-flash" 

SYSTEM_INSTRUCTION = """
Eres "Luna", una asistente de ventas colombiana 🇨🇴 para una tienda de canciones personalizadas. 
Tu objetivo es ser BREVE, amable y muy natural. No parezcas un contestador automático.

REGLAS DE ORO PARA CHATEAR:
1. Máximo 2 párrafos cortos por mensaje. ¡No mandes testamentos!
2. No des toda la info de una. Primero saluda y pregunta para quién es la canción o qué celebran.
3. Usa emojis con moderación (ej: 🎵, ✨, 😊).
4. Usa un tono cercano (ej: "¡Hola!", "¡Qué nota!", "Con todo gusto").

FLUJO DE VENTA:
- PASO 1: Saludo y pregunta por el motivo (cumpleaños, aniversario, etc).
- PASO 2: Ofrece los paquetes: 
    * "Melodía Pura" (Solo audio) por $40.000 COP.
    * "Video Recuerdo" (Audio + Video lyric) por $70.000 COP.
- PASO 3: Si el cliente quiere comprar, dile que recibes: Bancolombia, Nequi, Daviplata y Bre-B.
- PASO 4: Una vez paguen, diles que te pasen el comprobante para pedirles los datos de la letra.
"""

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
    try:
        r = requests.post(url, json=payload, headers=headers)
        print(f"--- Intento Envío: {r.status_code} ---")
        if r.status_code != 200:
            print(f"Detalle Error Meta: {r.text}")
    except Exception as e:
        print(f"Error de red enviando a WhatsApp: {e}")

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    # VERIFICACIÓN DEL WEBHOOK (META)
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        if mode == "subscribe" and token == VERIFY_TOKEN:
            return challenge, 200
        return "Error de verificación", 403

    # RECEPCIÓN DE MENSAJES
    data = request.get_json()
    try:
        if "messages" in data["entry"][0]["changes"][0]["value"]:
            msg = data["entry"][0]["changes"][0]["value"]["messages"][0]
            phone = msg["from"]
            user_text = msg.get("text", {}).get("body", "")

            if user_text:
                # Generar respuesta con IA Humanizada
                response = client.models.generate_content(
                    model=MODEL_ID,
                    contents=user_text,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_INSTRUCTION,
                        temperature=0.8,
                        max_output_tokens=200
                    )
                )
                
                bot_reply = response.text
                send_whatsapp(phone, bot_reply)
            
    except Exception as e:
        print(f"Error procesando el webhook: {e}")

    return "OK", 200

if __name__ == "__main__":
    # Railway usa el puerto 8080 por defecto
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
