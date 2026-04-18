import sqlite3
import os

db_path = r"c:\Users\Ciencia de DAtos\OneDrive - CONNECTA S.A.S\Escritorio\Varios\Whap_para _call\backend\bot_data.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    cursor.execute("SELECT interviewer_name, COUNT(*) FROM quota_submissions GROUP BY interviewer_name")
    rows = cursor.fetchall()
    print("Interviewer Name | Count")
    print("-" * 30)
    for row in rows:
        print(f"{row[0]} | {row[1]}")
except Exception as e:
    print(f"Error: {e}")

conn.close()
