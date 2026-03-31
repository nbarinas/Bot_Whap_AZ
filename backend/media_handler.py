import os
import requests
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Configuration
SERVICE_ACCOUNT_FILE = os.path.join(os.path.dirname(__file__), 'service_account.json')
SCOPES = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']

# These will be provided by the user or set as environment variables
DRIVE_FOLDER_ID = os.getenv("DRIVE_FOLDER_ID", "") 
SHEET_ID = os.getenv("SHEET_ID", "")

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "EAAXs5LUMDHoBQ052ePZAxW647UmCHi8OEdfACZABBXDKcITJiCow61lHT7njd1jI5ZALx73JNz2JDrpNUzISjHxZBZBny7Tm2LHfLdL72KmYGkZCs3oOSXftcUxazKFHt2z4IrRFko9oWXorQbhwaLHoUkBlIgmSVkCF4LhPDbSV3fnwK3EwfZCqLpbfZB62jwZDZD")

def get_drive_service():
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        print(f"ERROR: {SERVICE_ACCOUNT_FILE} not found.")
        return None
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return build('drive', 'v3', credentials=creds)

def get_sheets_service():
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        print(f"ERROR: {SERVICE_ACCOUNT_FILE} not found.")
        return None
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return build('sheets', 'v4', credentials=creds)

def download_whatsapp_media(media_id, save_path):
    """
    Downloads media from WhatsApp using Meta API.
    """
    url = f"https://graph.facebook.com/v22.0/{media_id}"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
    
    try:
        # Get media URL
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        media_url = response.json().get("url")
        
        if not media_url:
            print("Error: media URL not found in Meta response.")
            return None
            
        # Download actual file
        media_resp = requests.get(media_url, headers=headers)
        media_resp.raise_for_status()
        
        with open(save_path, "wb") as f:
            f.write(media_resp.content)
            
        print(f"Media downloaded and saved to {save_path}")
        return save_path
    except Exception as e:
        print(f"Error downloading WhatsApp media: {e}")
        return None

def upload_to_drive(file_path, filename, folder_id=None):
    """
    Uploads a local file to Google Drive.
    """
    service = get_drive_service()
    if not service: return None
    
    if not folder_id:
        folder_id = DRIVE_FOLDER_ID
        
    file_metadata = {
        'name': filename,
        'parents': [folder_id] if folder_id else []
    }
    
    try:
        media = MediaFileUpload(file_path, resumable=True)
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        drive_id = file.get('id')
        print(f"File uploaded to Drive. ID: {drive_id}")
        return drive_id
    except Exception as e:
        print(f"Error uploading to Drive: {e}")
        return None

def log_to_sheets(values, sheet_id=None):
    """
    Appends a row to a Google Sheet.
    values: list of data [Censo, Name, Neighborhood, Address, Date, Time, Drive Link 1, Drive Link 2]
    """
    service = get_sheets_service()
    if not service: return None
    
    if not sheet_id:
        sheet_id = SHEET_ID
        
    if not sheet_id:
        print("Error: SHEET_ID not provided.")
        return None

    body = {
        'values': [values]
    }
    
    try:
        result = service.spreadsheets().values().append(
            spreadsheetId=sheet_id, 
            range='Hoja 1!A1', # Assuming default sheet name in Spanish or 'Sheet1'
            valueInputOption='RAW', 
            body=body
        ).execute()
        return result
    except Exception as e:
        # Try again with 'Sheet1' if 'Hoja 1' fails
        try:
            result = service.spreadsheets().values().append(
                spreadsheetId=sheet_id, 
                range='Sheet1!A1', 
                valueInputOption='RAW', 
                body=body
            ).execute()
            return result
        except Exception as e2:
            print(f"Error logging to Sheets: {e2}")
            return None
