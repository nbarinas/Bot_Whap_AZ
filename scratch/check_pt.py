import sqlite3
import os

db_path = r"c:\Users\Ciencia de DAtos\OneDrive - CONNECTA S.A.S\Escritorio\Varios\Whap_para _call\backend\bot_data.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("SELECT study_code, COUNT(*) FROM bot_quotas WHERE category = 'Tipo de Punto' GROUP BY study_code")
rows = cursor.fetchall()

print("Study Code | Point Type Count")
print("-" * 30)
for row in rows:
    print(f"{row[0]} | {row[1]}")

conn.close()
