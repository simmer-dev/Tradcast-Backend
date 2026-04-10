"""
Notification microservice with SQLite persistence.
Run: pip install fastapi uvicorn aiosqlite databases && python scripts/notification_server.py
"""
import os
import sqlite3
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Query
from pydantic import BaseModel

DB_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(DB_DIR, "notifications.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            fid TEXT PRIMARY KEY,
            notifications_read INTEGER NOT NULL DEFAULT 0,
            last_read_at REAL
        );

        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fid TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at REAL NOT NULL,
            FOREIGN KEY (fid) REFERENCES users(fid)
        );

        CREATE INDEX IF NOT EXISTS idx_notif_fid_created
            ON notifications(fid, created_at DESC);

        -- broadcast notifications go to every user
        CREATE TABLE IF NOT EXISTS broadcast_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message TEXT NOT NULL,
            created_at REAL NOT NULL
        );
    """)
    conn.commit()
    conn.close()


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_user(conn: sqlite3.Connection, fid: str):
    row = conn.execute("SELECT fid FROM users WHERE fid = ?", (fid,)).fetchone()
    if not row:
        conn.execute(
            "INSERT INTO users (fid, notifications_read) VALUES (?, 0)", (fid,)
        )
        conn.commit()


def get_latest_notifications(conn: sqlite3.Connection, fid: str, limit: int = 6):
    """Merge per-user + broadcast notifications, return newest first."""
    rows = conn.execute(
        """
        SELECT message, created_at FROM notifications WHERE fid = ?
        UNION ALL
        SELECT message, created_at FROM broadcast_notifications
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (fid, limit),
    ).fetchall()
    return [{"message": r["message"], "created_at": r["created_at"]} for r in rows]


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(lifespan=lifespan)


# ──────────────────────────────────────────────
# GET  /notification?fid=0x...
# ──────────────────────────────────────────────
@app.get("/notification")
def get_notifications(fid: str = Query(...)):
    fid = fid.lower().strip()
    print(fid)
    conn = get_conn()
    ensure_user(conn, fid)
    notifs = get_latest_notifications(conn, fid.lower().strip())
    print(notifs)

    user = conn.execute(
        "SELECT notifications_read FROM users WHERE fid = ?", (fid.lower().strip(),)
    ).fetchone()
    print(user)

    conn.close()
    return {
        "notification": [n["message"] for n in notifs],
        "notifications_read": bool(user["notifications_read"]),
    }


# ──────────────────────────────────────────────
# POST /notifications/click  — mark read
# ──────────────────────────────────────────────
class ClickPayload(BaseModel):
    notification_clicked: str
    fid: str


@app.post("/notifications/click")
def click_notifications(payload: ClickPayload):
    conn = get_conn()
    ensure_user(conn, payload.fid.lower().strip())
    conn.execute(
        "UPDATE users SET notifications_read = 1, last_read_at = ? WHERE fid = ?",
        (time.time(), payload.fid.lower().strip()),
    )
    conn.commit()
    conn.close()
    return {"success": True}


# ──────────────────────────────────────────────
# POST /notification/push?fid=0x...  — send to one user
# ──────────────────────────────────────────────
class PushPayload(BaseModel):
    fid: str
    message: str


@app.post("/notification/push")
def push_notification(payload: PushPayload):
    conn = get_conn()
    ensure_user(conn, payload.fid.lower().strip())
    now = time.time()
    conn.execute(
        "INSERT INTO notifications (fid, message, created_at) VALUES (?, ?, ?)",
        (payload.fid.lower().strip(), payload.message, now),
    )
    conn.execute(
        "UPDATE users SET notifications_read = 0 WHERE fid = ?", (payload.fid.lower().strip(),)
    )
    conn.commit()
    conn.close()
    return {"success": True}


# ──────────────────────────────────────────────
# POST /notification/broadcast  — send to ALL users
# ──────────────────────────────────────────────
class BroadcastPayload(BaseModel):
    message: str


@app.post("/notification/broadcast")
def broadcast_notification(payload: BroadcastPayload):
    conn = get_conn()
    now = time.time()
    conn.execute(
        "INSERT INTO broadcast_notifications (message, created_at) VALUES (?, ?)",
        (payload.message, now),
    )
    conn.execute("UPDATE users SET notifications_read = 0")
    conn.commit()
    total_users = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
    conn.close()
    return {"success": True, "reached_users": total_users}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=6009)
