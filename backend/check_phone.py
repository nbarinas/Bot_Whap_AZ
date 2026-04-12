import requests
import json

WHATSAPP_TOKEN = "EAAXs5LUMDHoBQ052ePZAxW647UmCHi8OEdfACZABBXDKcITJiCow61lHT7njd1jI5ZALx73JNz2JDrpNUzISjHxZBZBny7Tm2LHfLdL72KmYGkZCs3oOSXftcUxazKFHt2z4IrRFko9oWXorQbhwaLHoUkBlIgmSVkCF4LhPDbSV3fnwK3EwfZCqLpbfZB62jwZDZD"
PHONE_ID = "969902462880750"

url = f"https://graph.facebook.com/v22.0/{PHONE_ID}"
headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}

response = requests.get(url, headers=headers)
print(f"PHONE ID {PHONE_ID} DETAILS:")
print(response.text)
