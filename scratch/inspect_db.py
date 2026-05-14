import sqlite3
import os

db_path = 'az_marketing.db'
if not os.path.exists(db_path):
    print(f"File {db_path} not found")
else:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print("Tables:", tables)
    
    if ('calls',) in tables:
        cursor.execute("PRAGMA table_info(calls);")
        print("Schema of 'calls':", cursor.fetchall())
    else:
        print("'calls' table NOT found in az_marketing.db")
    conn.close()
