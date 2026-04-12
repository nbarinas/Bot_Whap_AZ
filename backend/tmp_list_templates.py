import requests
import json

WHATSAPP_TOKEN = "EAAXs5LUMDHoBQ052ePZAxW647UmCHi8OEdfACZABBXDKcITJiCow61lHT7njd1jI5ZALx73JNz2JDrpNUzISjHxZBZBny7Tm2LHfLdL72KmYGkZCs3oOSXftcUxazKFHt2z4IrRFko9oWXorQbhwaLHoUkBlIgmSVkCF4LhPDbSV3fnwK3EwfZCqLpbfZB62jwZDZD"
WABA_ID = "1431048488756614"

url = f"https://graph.facebook.com/v22.0/{WABA_ID}/phone_numbers"
headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}

response = requests.get(url, headers=headers)
print("PHONE NUMBERS:")
print(response.text)

url_me = "https://graph.facebook.com/v22.0/me/whatsapp_business_accounts"
response_me = requests.get(url_me, headers=headers)
print("WABA ACCOUNTS:")
print(response_me.text)

# We can also try getting phone numbers for the ID in main.py if it's different
# url_special = "https://graph.facebook.com/v22.0/969902462880750"
# response_special = requests.get(url_special, headers=headers)
# print("\nPHONE ID 969902462880750 info:")
# print(response_special.text)
