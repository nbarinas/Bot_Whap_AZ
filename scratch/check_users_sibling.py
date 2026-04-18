import sqlite3
import os

db_path = r"c:\Users\Ciencia de DAtos\OneDrive - CONNECTA S.A.S\Escritorio\Varios\az\az_marketing.db"
if not os.path.exists(db_path):
    print("DB not found at " + db_path)
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    cursor.execute("SELECT id, username, full_name FROM users WHERE full_name LIKE '%Felipe%' OR username LIKE '%Felipe%'")
    rows = cursor.fetchall()
    print("ID | Username | Full Name")
    print("-" * 40)
    for row in rows:
        print(f"{row[0]} | {row[1]} | {row[2]}")
except Exception as e:
    print(f"Error: {e}")

conn.close()
