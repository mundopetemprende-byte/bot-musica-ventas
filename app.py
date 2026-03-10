import os
import requests
from flask import Flask, request
from google import genai
from google.genai import types

app = Flask(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")

client = genai.Client(api_key=GEMINI_API_KEY)
# Probemos con el 2.0 que ya te había reconocido antes:
MODEL_ID = "gemini-2.0-flash" 

SYSTEM_INSTRUCTION = """
Eres "Luna", asistente de ventas en Colombia 🇨🇴. 
Breve (2-3 líneas), amable, ofrece canciones: Melodía Pura ($40k) y Video Recuerdo ($70k). 
Pagos: Bancolombia, Nequi, Daviplata y Bre-B.
"""

def send_whatsapp(to_phone, text):
    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to_phone, "type": "text", "text": {"body": text}}
    requests.post(url, json=payload, headers=headers)

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        if request.args.get("hub.verify_token") == VERIFY_TOKEN:
            return request.args.get("hub.challenge"), 200
        return "Error", 403

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
                # LLAMADA LIMPIA AL MODELO
                response = client.models.generate_content(
                    model=MODEL_ID,
                    contents=user_text,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_INSTRUCTION,
                        temperature=0.7,
                        max_output_tokens=150
                    )
                )
                send_whatsapp(phone, response.text)
    except Exception as e:
        print(f"Error detectado: {e}")

    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
