"""
FastAPI endpoints for prize-winner operations.

Run:
  uvicorn scripts.prize_winners_api:app --reload --port 8010
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Generator, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

DB_PATH = os.getenv(
    "TELEGRAM_ROUNDS_DB_PATH",
    "", # sqlite db location
)

app = FastAPI(title="Tradcast Prize Winners API", version="1.0.0")


@contextmanager
def get_conn() -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


class MarkPrizeSentBody(BaseModel):
    wallet: str = Field(..., min_length=42, max_length=42)
    round_id: Optional[str] = None


@app.get("/prize-winners")
def get_prize_winners(round_id: Optional[str] = None, only_unsent: bool = False):
    try:
        with get_conn() as conn:
            clauses = ["winner_rank <= 5"]
            params: list[object] = []
            if round_id:
                clauses.append("round_id = ?")
                params.append(round_id)
            if only_unsent:
                clauses.append("prize_sent = 0")
            where_sql = " AND ".join(clauses)
            query = f"""
                SELECT
                  round_id,
                  winner_rank,
                  wallet,
                  participant_id,
                  auth_type,
                  fid,
                  code,
                  prize_sent,
                  submitted_at_ms
                FROM round_winners
                WHERE {where_sql}
                ORDER BY submitted_at_ms ASC
            """
            rows = conn.execute(query, params).fetchall()
            return {
                "count": len(rows),
                "winners": [
                    {
                        "round_id": row["round_id"],
                        "winner_rank": row["winner_rank"],
                        "wallet": row["wallet"],
                        "participant_id": row["participant_id"],
                        "auth_type": row["auth_type"],
                        "fid": row["fid"],
                        "code": row["code"],
                        "prize_sent": bool(row["prize_sent"]),
                        "submitted_at_ms": row["submitted_at_ms"],
                    }
                    for row in rows
                ],
            }
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail=f"Database error: {exc}") from exc


@app.patch("/prize-winners/mark-sent")
def mark_prize_sent(body: MarkPrizeSentBody):
    wallet = body.wallet.lower()
    try:
        with get_conn() as conn:
            if body.round_id:
                result = conn.execute(
                    """
                    UPDATE round_winners
                    SET prize_sent = 1
                    WHERE wallet = ? AND round_id = ? AND winner_rank <= 5
                    """,
                    (wallet, body.round_id),
                )
            else:
                result = conn.execute(
                    """
                    UPDATE round_winners
                    SET prize_sent = 1
                    WHERE wallet = ? AND winner_rank <= 5
                    """,
                    (wallet,),
                )
            conn.commit()

            if result.rowcount == 0:
                raise HTTPException(
                    status_code=404,
                    detail="No matching winner rows found for wallet/round.",
                )
            return {
                "ok": True,
                "updated_rows": result.rowcount,
                "wallet": wallet,
                "round_id": body.round_id,
            }
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail=f"Database error: {exc}") from exc
