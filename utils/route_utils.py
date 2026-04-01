from datetime import datetime, timezone, timedelta
from google.cloud import firestore
from google.cloud.firestore_v1 import SERVER_TIMESTAMP


async def handle_streak(fid: str, user, firestore_manager) -> dict:
    """Handle daily streak logic. Returns a dict of fields that were updated
    so the caller can merge them into the local user dict without re-reading."""
    now = datetime.now(timezone.utc)

    last_online = user.get("last_online")

    if not last_online or last_online is SERVER_TIMESTAMP:
        await firestore_manager.update_user(fid, {
            "streak_days": 1,
            "last_online": firestore.SERVER_TIMESTAMP,
        })
        return {"streak_days": 1, "last_online": now}

    last_date = last_online.date()
    today = now.date()
    yesterday = today - timedelta(days=1)

    if last_date == today:
        return {}

    if last_date == yesterday:
        new_streak = user.get("streak_days", 0) + 1
        await firestore_manager.update_user(fid, {
            "streak_days": firestore.Increment(1),
            "daily_games": 0,
            "last_online": firestore.SERVER_TIMESTAMP,
        })
        return {"streak_days": new_streak, "daily_games": 0, "last_online": now}

    await firestore_manager.update_user(fid, {
        "streak_days": 1,
        "daily_games": 0,
        "last_online": firestore.SERVER_TIMESTAMP,
    })
    return {"streak_days": 1, "daily_games": 0, "last_online": now}

