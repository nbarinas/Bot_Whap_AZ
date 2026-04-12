import requests
import json

WHATSAPP_TOKEN = "EAAXs5LUMDHoBQ052ePZAxW647UmCHi8OEdfACZABBXDKcITJiCow61lHT7njd1jI5ZALx73JNz2JDrpNUzISjHxZBZBny7Tm2LHfLdL72KmYGkZCs3oOSXftcUxazKFHt2z4IrRFko9oWXorQbhwaLHoUkBlIgmSVkCF4LhPDbSV3fnwK3EwfZCqLpbfZB62jwZDZD"
PHONE_ID = "969902462880750"
TO_PHONE = "573136623816"

url = f"https://graph.facebook.com/v22.0/{PHONE_ID}/messages"
headers = {
    "Authorization": f"Bearer {WHATSAPP_TOKEN}",
    "Content-Type": "application/json"
}

data = {
    "messaging_product": "whatsapp",
    "to": TO_PHONE,
    "type": "template",
    "template": {
        "name": "recordatorio_de_llamada",
        "language": {
            "code": "es_CO"
        },
        "components": [
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": "Cristian (Test)"},
                    {"type": "text", "text": "11:30 AM"},
                    {"type": "text", "text": "Estudio de Mercado"},
                    {"type": "text", "text": "3136139581"},
                    {"type": "text", "text": "Diana Buitrago"}
                ]
            }
        ]
    }
}

response = requests.post(url, headers=headers, data=json.dumps(data))
print(f"Status: {response.status_code}")
print(f"Response: {response.text}")
