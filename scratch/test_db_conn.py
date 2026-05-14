import pymysql
import os

# Este script intenta conectar al servidor MySQL que falla en los logs
# para determinar si es un problema de conectividad general o solo de Render.

DB_IP = "162.254.201.255"
# Estos valores deberían venir de tu DATABASE_URL en Render
# Por ejemplo: mysql://user:password@162.254.201.255:3306/dbname
DB_USER = "pon_tu_usuario_aqui" 
DB_PASS = "pon_tu_password_aqui"
DB_NAME = "pon_tu_db_aqui"

def test_connection():
    print(f"Intentando conectar a {DB_IP}...")
    try:
        conn = pymysql.connect(
            host=DB_IP,
            user=DB_USER,
            password=DB_PASS,
            database=DB_NAME,
            connect_timeout=10 # 10 segundos de gracia
        )
        print("✅ ¡Conexión exitosa desde el entorno local!")
        conn.close()
    except pymysql.err.OperationalError as e:
        if e.args[0] == 2003:
            print(f"❌ ERROR: El servidor en {DB_IP} no responde (Timed Out).")
            print("Esto confirma que la IP es inaccesible desde tu red actual.")
        else:
            print(f"❌ Error operacional: {e}")
    except Exception as e:
        print(f"❌ Error inesperado: {e}")

if __name__ == "__main__":
    test_connection()
