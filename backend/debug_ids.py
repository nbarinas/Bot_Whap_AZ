import requests
import json

WHATSAPP_TOKEN = "EAAXs5LUMDHoBQ052ePZAxW647UmCHi8OEdfACZABBXDKcITJiCow61lHT7njd1jI5ZALx73JNz2JDrpNUzISjHxZBZBny7Tm2LHfLdL72KmYGkZCs3oOSXftcUxazKFHt2z4IrRFko9oWXorQbhwaLHoUkBlIgmSVkCF4LhPDbSV3fnwK3EwfZCqLpbfZB62jwZDZD"

# Try getting all WABA IDs first
url = "https://graph.facebook.com/v22.0/me?fields=whatsapp_business_accounts"
headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}

response = requests.get(url, headers=headers)
print("WABAs associated with this token:")
print(response.text)

data = response.json()
if "whatsapp_business_accounts" in data:
    for waba in data["whatsapp_business_accounts"]["data"]:
        waba_id = waba["id"]
        print(f"\nChecking WABA: {waba_id} ({waba.get('name', 'Unnamed')})")
        # List Phone Numbers for THIS WABA
        response_pn = requests.get(f"https://graph.facebook.com/v22.0/{waba_id}/phone_numbers", headers=headers)
        print(f"PHONE NUMBERS for WABA {waba_id}:")
        print(response_pn.text)
        
        # List Templates for THIS WABA
        response_tm = requests.get(f"https://graph.facebook.com/v22.0/{waba_id}/message_templates", headers=headers)
        print(f"TEMPLATES for WABA {waba_id}:")
        # Just names
        tm_data = response_tm.json().get("data", [])
        for tm in tm_data:
            print(f" - {tm['name']} ({tm['language']})")
else:
    print("\nNo WABAs found via /me?fields=whatsapp_business_accounts")
