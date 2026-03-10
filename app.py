import os
import requests
from flask import Flask, request
from google import genai
from google.genai import types

app = Flask(__name__)

# --- CONFIGURACIÓN DE VARIABLES ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")

# Configuración del Cliente
client = genai.Client(api_key=GEMINI_API_KEY)
# El nombre técnico correcto para el SDK es este:
MODEL_ID = "gemini-1.5-flash" 

SYSTEM_INSTRUCTION = """
Eres "Luna", la vendedora estrella de canciones personalizadas en Colombia 🇨🇴.
Tu meta es cerrar ventas de forma humana, breve y eficiente. 

ESTRATEGIA DE VENTA:
1. BREVEDAD: Máximo 2-3 líneas. No aburras al cliente con textos largos.
2. EMPATÍA: Saluda y pregunta el motivo del regalo (ej. cumpleaños, aniversario).
3. PRECIOS: 
   - "Melodía Pura" (Solo audio) por $40.000 COP.
   - "Video Recuerdo" (Audio + Video lyric) por $70.000 COP.
4. PAGOS: Recibes Bancolombia, Nequi, Daviplata y Bre-B.
5. CIERRE: Pide el comprobante para iniciar la creación.
"""

def send_whatsapp(to_phone, text):
    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to_phone, "type": "text", "text": {"body": text}}
    try:
        r = requests.post(url, json=payload, headers=headers)
        if r.status_code != 200:
            print(f"Error Meta: {r.text}")
    except Exception as e:
        print(f"Error conexión WhatsApp: {e}")

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    # Verificación del Webhook
    if request.method == "GET":
        if request.args.get("hub.verify_token") == VERIFY_TOKEN:
            return request.args.get("hub.challenge"), 200
        return "Error de verificación", 403

    # Recepción de mensajes
    data = request.get_json()
    try:
        entry = data.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0]
        value = changes.get("value", {})
        
        if "messages" in value:
            msg = value["messages"][0]
            phone = msg["from"]
            user_text = msg.get("text", {}).get("body", "")

            if user_text:
                # Generar respuesta de Luna
                response = client.models.generate_content(
                    model=MODEL_ID,
                    contents=user_text,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_INSTRUCTION,
                        temperature=0.7,
                        max_output_tokens=150
                    )
                )
                
                # Enviar de vuelta a WhatsApp
                send_whatsapp(phone, response.text)
                
    except Exception as e:
        # Si es un error de cuota (429), lo veremos en los logs
        if "429" in str(e):
            print("🚨 AGOTADO: Google bloqueó la cuota gratuita por un momento.")
        else:
            print(f"Error en flujo: {e}")

    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
