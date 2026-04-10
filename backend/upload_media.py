import requests
import os
import json

# Credenciales actualizadas por el usuario
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "EAAXs5LUMDHoBQ3gidC32OLGzDEZC4uhZCAWI0WNVvk8nnKg4ewiYo4a0pQi9qhjhXwAZC94UoSg6BsPQzFqjPIYiTu6rQqkhqihEbIG5zfKTpqN3tcrce9dUR4UOCYR7qKYov3IILAcUcQUJjuAIZBZBo5koizRGSI7vBUkmD8nV2aK8xqwLAfoCR3MWWvAG6sF5GfInh5sBdQz6nPsR9fowIYhkKK3f8r80r5GJHTlSohpiWwEZB7rowThW38oH3PANfXZANosc8sFhZBwYKAaCZAR719T0ZA9rUZD")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID", "969902462880750")

def upload_media(file_path, mime_type):
    url = f"https://graph.facebook.com/v22.0/{WHATSAPP_PHONE_ID}/media"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}"
    }
    files = {
        "file": (os.path.basename(file_path), open(file_path, "rb"), mime_type),
        "messaging_product": (None, "whatsapp")
    }
    
    print(f"Subiendo {file_path}...")
    response = requests.post(url, headers=headers, files=files)
    
    if response.status_code == 200:
        media_id = response.json().get("id")
        print(f"Éxito! Media ID: {media_id}")
        return media_id
    else:
        print(f"Error subiendo {file_path}: {response.text}")
        return None

if __name__ == "__main__":
    # Rutas relativas desde la raíz del proyecto
    image_path = "Para bono.jpeg"
    video_path = "Video Bono Comprimido.mp4"
    
    image_id = upload_media(image_path, "image/jpeg")
    video_id = upload_media(video_path, "video/mp4")
    
    result = {
        "image_id": image_id,
        "video_id": video_id
    }
    
    with open("backend/media_ids.json", "w") as f:
        json.dump(result, f, indent=4)
    
    print("\nIDs guardados en backend/media_ids.json")
