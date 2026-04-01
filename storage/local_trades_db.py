import sqlite3
import json
import os
import time
import threading
from typing import List, Dict, Any

MAX_ROWS = 10_000

_DB_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_PATH = os.path.join(_DB_DIR, "trade_decisions.db")


class LocalTradesDB:
    """
    SQLite-backed local store for trade decisions.

    Keeps at most MAX_ROWS rows (oldest pruned automatically).
    Uses WAL journal mode for safe concurrent access from multiple processes
    (e.g. tradcast_main and tradcast_game on the same machine).
    """

    def __init__(self, db_path: str = _DB_PATH):
        self._db_path = db_path
        self._local = threading.local()
        self._init_table()

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self._db_path, timeout=10)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            self._local.conn = conn
        return conn

    def _init_table(self):
        c = self._conn()
        c.execute("""
            CREATE TABLE IF NOT EXISTS trade_decisions (
                id            TEXT PRIMARY KEY,
                fid           TEXT NOT NULL,
                trade_env_id  TEXT,
                actions       TEXT,
                final_pnl     REAL,
                final_profit  REAL,
                created_at    REAL NOT NULL
            )
        """)
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_td_fid_created "
            "ON trade_decisions (fid, created_at DESC)"
        )
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_td_created "
            "ON trade_decisions (created_at)"
        )
        c.commit()

    # ── writes ────────────────────────────────────────────────

    def insert_trade(
        self,
        session_id: str,
        fid: str,
        trade_env_id: str,
        actions: list,
        final_pnl: float,
        final_profit: float,
    ):
        """Insert a full trade record (game servers call this)."""
        c = self._conn()
        c.execute(
            "INSERT OR REPLACE INTO trade_decisions "
            "(id, fid, trade_env_id, actions, final_pnl, final_profit, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (session_id, fid, trade_env_id, json.dumps(actions), final_pnl, final_profit, time.time()),
        )
        c.commit()
        self._prune(c)

    def insert_trade_summary(
        self,
        session_id: str,
        fid: str,
        trade_env_id: str,
        final_pnl: float,
        final_profit: float,
        created_at: float,
    ):
        """Insert a lightweight summary (no actions). Used by main server for cross-server sync."""
        c = self._conn()
        c.execute(
            "INSERT OR IGNORE INTO trade_decisions "
            "(id, fid, trade_env_id, actions, final_pnl, final_profit, created_at) "
            "VALUES (?, ?, ?, NULL, ?, ?, ?)",
            (session_id, fid, trade_env_id, final_pnl, final_profit, created_at),
        )
        c.commit()
        self._prune(c)

    # ── reads ─────────────────────────────────────────────────

    def get_latest_trades(self, fid: str, limit: int = 4) -> List[Dict[str, Any]]:
        rows = self._conn().execute(
            "SELECT final_pnl, final_profit, created_at "
            "FROM trade_decisions WHERE fid = ? ORDER BY created_at DESC LIMIT ?",
            (fid, limit),
        ).fetchall()
        return [
            {"final_pnl": r["final_pnl"], "final_profit": r["final_profit"], "created_at": r["created_at"]}
            for r in rows
        ]

    def count(self) -> int:
        return self._conn().execute("SELECT COUNT(*) FROM trade_decisions").fetchone()[0]

    # ── deletes ───────────────────────────────────────────────

    def delete_by_fid(self, fid: str):
        c = self._conn()
        c.execute("DELETE FROM trade_decisions WHERE fid = ?", (fid,))
        c.commit()

    # ── maintenance ───────────────────────────────────────────

    def _prune(self, conn: sqlite3.Connection):
        row_count = conn.execute("SELECT COUNT(*) FROM trade_decisions").fetchone()[0]
        if row_count > MAX_ROWS:
            excess = row_count - MAX_ROWS
            conn.execute(
                "DELETE FROM trade_decisions WHERE id IN "
                "(SELECT id FROM trade_decisions ORDER BY created_at ASC LIMIT ?)",
                (excess,),
            )
            conn.commit()


trades_db = LocalTradesDB()
print(f"LocalTradesDB: {trades_db.count()} rows in {_DB_PATH}")
