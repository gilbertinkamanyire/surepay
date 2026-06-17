import sqlite3
import os

db_path = 'database.db'
if os.path.exists(db_path):
    db = sqlite3.connect(db_path)
    cursor = db.cursor()
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN reset_token TEXT')
    except Exception as e:
        print(f"reset_token: {e}")
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN reset_token_expiry TIMESTAMP')
    except Exception as e:
        print(f"reset_token_expiry: {e}")
    db.commit()
    db.close()
    print("Migration done.")
else:
    print("DB doesn't exist.")
