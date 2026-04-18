import sqlite3
db_path = r"c:\Users\Ciencia de DAtos\OneDrive - CONNECTA S.A.S\Escritorio\Varios\az_marketing.db"
conn = sqlite3.connect(db_path)
print(conn.execute("SELECT id, username, full_name FROM users WHERE full_name LIKE '%Felipe%'").fetchall())
conn.close()
