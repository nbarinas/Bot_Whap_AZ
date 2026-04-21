import pymysql
import os
import time

# Hostinger MySQL Connection Details from Logs
DB_HOST = "162.254.201.255"
DB_PORT = 3306

def test_raw_connection():
    print(f"--- Diagnóstico de Conexión MySQL ---")
    print(f"Intentando conectar a {DB_HOST}:{DB_PORT}...")
    
    start_time = time.time()
    try:
        # Intentar una conexión TCP básica antes de usar el driver de MySQL
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((DB_HOST, DB_PORT))
        
        if result == 0:
            print(f"✅ ÉXITO: El puerto {DB_PORT} en {DB_HOST} está ABIERTO.")
        else:
            print(f"❌ ERROR: El puerto {DB_PORT} en {DB_HOST} está CERRADO o BLOQUEADO (Código: {result}).")
            print(f"Esto confirma un problema de FIREWALL o que el servidor está caído.")
            return

        # Si el puerto está abierto, intentar con PyMySQL (requiere credenciales)
        # Nota: Estas credenciales deberían tomarse de la DATABASE_URL si estuviera disponible localmente
        print(f"\nEl puerto está respondiendo. Si aún falla en Render, es probable que Render esté en la lista negra (Blacklist) del servidor.")
        
    except Exception as e:
        print(f"❌ Error durante el diagnóstico: {e}")
    finally:
        elapsed = time.time() - start_time
        print(f"\nTiempo transcurrido: {elapsed:.2f} segundos")

if __name__ == "__main__":
    test_raw_connection()
