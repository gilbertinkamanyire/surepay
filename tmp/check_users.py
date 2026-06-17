import sqlite3
import os

db_path = 'database.db'
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        users = cursor.execute("SELECT username, role, is_verified FROM users WHERE role = 'lecturer'").fetchall()
        print([dict(u) for u in users])
    except Exception as e:
        print(f"Error: {e}")
    conn.close()
else:
    print("Database not found")
