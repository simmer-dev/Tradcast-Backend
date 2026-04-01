import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional


class LeaderboardService:
    """
    In-memory leaderboard backed by Firestore 'leaderboard_scores' collection.

    Scores live in RAM for zero-cost reads. Firestore is the durable store,
    written by game servers on every score change. This service only reads
    Firestore on startup and writes during periodic resets.
    """

    COLLECTION = "leaderboard_scores"
    PERIODS = ("daily_score", "weekly_score", "monthly_score")

    def __init__(self, db, users_cache, users_collection: str = "users"):
        self.db = db
        self._scores: Dict[str, Dict[str, Any]] = {}
        self._users_collection = users_collection
        self._users_cache = users_cache

    # ── bootstrap ─────────────────────────────────────────────

    async def load(self):
        """Read the full leaderboard_scores collection into memory (once on startup)."""
        docs = await self.db.collection(self.COLLECTION).get()
        missing_count = 0
        for doc in docs:
            data = doc.to_dict()
            if not data.get("username"):
                uname = self._resolve_username(doc.id)
                if uname != "Unknown":
                    data["username"] = uname
                    missing_count += 1
            self._scores[doc.id] = data
        print(
            f"LeaderboardService: loaded {len(self._scores)} entries into memory"
            + (f"  (backfilled {missing_count} missing usernames)" if missing_count else "")
        )

    # ── cache updates (called via /internal/update_score) ─────

    def _resolve_username(self, fid: str) -> str:
        """Look up username from users cache, falling back to 'Unknown'."""
        user = self._users_cache.get(fid)
        if user:
            return user.get("username", "Unknown")
        return "Unknown"

    def update_cache(self, fid: str, profit: float):
        """
        Update the in-memory leaderboard cache only.
        Firestore is already written by the game server that sent the notification.
        """
        if fid in self._scores:
            entry = self._scores[fid]
            for key in self.PERIODS:
                entry[key] = entry.get(key, 0) + profit
            if not entry.get("username") or entry["username"] == "Unknown":
                entry["username"] = self._resolve_username(fid)
        else:
            self._scores[fid] = {
                "daily_score": profit,
                "weekly_score": profit,
                "monthly_score": profit,
                "username": self._resolve_username(fid),
            }

    # ── leaderboard reads (pure in-memory, zero Firestore cost) ──

    def get_leaderboard(
        self,
        fid: str,
        period: str,
        top_n: int = 10,
        username: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Sort the in-memory cache and return the top-N entries plus the
        requesting user's entry (with their rank) if they aren't in the top N.
        """
        score_key = f"{period}_score"
        profit_key = f"{period}_profit"

        sorted_users = sorted(
            self._scores.items(),
            key=lambda x: x[1].get(score_key, 0),
            reverse=True,
        )

        leaderboard: List[Dict[str, Any]] = []
        user_in_top = False

        for idx, (user_fid, data) in enumerate(sorted_users[:top_n], start=1):
            is_user = user_fid == fid
            if is_user:
                user_in_top = True
            leaderboard.append({
                "username": data.get("username", "Unknown"),
                profit_key: data.get(score_key, 0),
                "the_user": is_user,
                "rank": idx,
            })

        if not user_in_top:
            user_rank = None
            for idx, (user_fid, _) in enumerate(sorted_users, start=1):
                if user_fid == fid:
                    user_rank = idx
                    break

            user_data = self._scores.get(fid, {})
            display_name = user_data.get("username") or username or "Unknown"

            leaderboard.append({
                "username": display_name,
                profit_key: user_data.get(score_key, 0),
                "the_user": True,
                "rank": user_rank if user_rank else len(sorted_users) + 1,
            })

        return leaderboard

    # ── periodic resets ───────────────────────────────────────

    async def _reset_period(self, field: str):
        """Zero out a single score field for every user in cache + Firestore."""
        for entry in self._scores.values():
            entry[field] = 0

        all_fids = list(self._scores.keys())
        for i in range(0, len(all_fids), 499):
            batch = self.db.batch()
            for fid in all_fids[i : i + 499]:
                doc_ref = self.db.collection(self.COLLECTION).document(fid)
                batch.update(doc_ref, {field: 0})
            await batch.commit()

        print(f"LeaderboardService: reset {field} for {len(all_fids)} users")

    def start_reset_loop(self):
        """Fire-and-forget background task for periodic score resets."""
        asyncio.create_task(self._reset_loop())

    async def _reset_loop(self):
        """Sleep until next 00:00 UTC, then reset the appropriate period(s)."""
        while True:
            try:
                now = datetime.now(timezone.utc)
                tomorrow = (now + timedelta(days=1)).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                wait_seconds = (tomorrow - now).total_seconds()
                print(
                    f"LeaderboardService: next reset in {wait_seconds:.0f}s "
                    f"at {tomorrow.isoformat()}"
                )
                await asyncio.sleep(wait_seconds)

                now = datetime.now(timezone.utc)

                await self._reset_period("daily_score")

                if now.weekday() == 0:  # Monday
                    await self._reset_period("weekly_score")

                if now.day == 1:
                    await self._reset_period("monthly_score")

            except Exception as e:
                print(f"LeaderboardService reset loop error: {e}")
                await asyncio.sleep(60)


# ---------------------------------------------------------------------------
# Singleton -- created at import time, loaded asynchronously via .load()
# ---------------------------------------------------------------------------
from storage.firestore_client import firestore_manager  # noqa: E402

leaderboard_service = LeaderboardService(
    db=firestore_manager.db,
    users_cache=firestore_manager._users_cache,
    users_collection=firestore_manager.users_collection,
)
