"""
One-time script: backfill missing 'username' in leaderboard_scores collection.

For each leaderboard_scores document that has no 'username' field,
look up the username from the 'users' collection (same fid) and write it.

Usage:
    python fix_leaderboard_usernames.py          # dry-run (shows what would change)
    python fix_leaderboard_usernames.py --apply  # actually write to Firestore
"""

import asyncio
import sys
from google.cloud.firestore_v1.async_client import AsyncClient

PROJECT = "miniapp-479712"
DATABASE = "default-clone"
USERS_COL = "users"
LB_COL = "leaderboard_scores"
BATCH_SIZE = 499


async def main():
    dry_run = "--apply" not in sys.argv
    if dry_run:
        print("=== DRY RUN (pass --apply to write) ===\n")
    else:
        print("=== APPLYING CHANGES ===\n")

    db = AsyncClient(project=PROJECT, database=DATABASE)

    print("Loading users collection...")
    user_docs = await db.collection(USERS_COL).get()
    users = {doc.id: doc.to_dict() for doc in user_docs}
    print(f"  -> {len(users)} users loaded\n")

    print("Loading leaderboard_scores collection...")
    lb_docs = await db.collection(LB_COL).get()
    print(f"  -> {len(lb_docs)} leaderboard entries loaded\n")

    to_fix = []
    for doc in lb_docs:
        data = doc.to_dict()
        if data.get("username"):
            continue
        fid = doc.id
        user = users.get(fid)
        if user and user.get("username"):
            to_fix.append((fid, user["username"]))

    if not to_fix:
        print("All leaderboard_scores documents already have a username. Nothing to fix.")
        return

    print(f"Found {len(to_fix)} documents missing username:\n")
    for fid, uname in to_fix:
        print(f"  {fid}  ->  {uname}")

    if dry_run:
        print(f"\nRe-run with --apply to write {len(to_fix)} updates.")
        return

    print(f"\nWriting {len(to_fix)} updates in batches of {BATCH_SIZE}...")
    written = 0
    for i in range(0, len(to_fix), BATCH_SIZE):
        batch = db.batch()
        chunk = to_fix[i : i + BATCH_SIZE]
        for fid, uname in chunk:
            ref = db.collection(LB_COL).document(fid)
            batch.update(ref, {"username": uname})
        await batch.commit()
        written += len(chunk)
        print(f"  batch committed: {written}/{len(to_fix)}")

    print(f"\nDone. Updated {written} leaderboard_scores documents.")


if __name__ == "__main__":
    asyncio.run(main())
