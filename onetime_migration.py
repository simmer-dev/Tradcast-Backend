"""
One-time migration: adds the 'email' column to the tickets table if it's missing.
Run once: python migrate_db.py
"""
import sqlite3

DB_PATH = 'invite_tracker.db'   # 👈 change if your .db file is elsewhere

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# Check existing columns
c.execute("PRAGMA table_info(tickets)")
columns = [row[1] for row in c.fetchall()]
print(f"Current columns: {columns}")

if 'email' not in columns:
    c.execute("ALTER TABLE tickets ADD COLUMN email TEXT DEFAULT 'Not provided'")
    conn.commit()
    print("✅ 'email' column added successfully.")
else:
    print("ℹ️  'email' column already exists, nothing to do.")

conn.close()
