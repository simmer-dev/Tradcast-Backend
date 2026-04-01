"""
Quick script to look up a user document from Firestore.

Usage:
    python get_user.py <fid>
"""

import sys
import asyncio
from google.cloud.firestore_v1.async_client import AsyncClient

PROJECT = "miniapp-479712"
DATABASE = "default-clone"
USERS_COL = "users"


async def main():
    if len(sys.argv) < 2:
        print("Usage: python get_user.py <fid>")
        sys.exit(1)

    fid = sys.argv[1].lower().strip()
    db = AsyncClient(project=PROJECT, database=DATABASE)

    doc = await db.collection(USERS_COL).document(fid).get()

    if not doc.exists:
        print(f"No user found with fid: {fid}")
        return

    data = doc.to_dict()
    print(f"\n{'=' * 50}")
    print(f"  FID: {fid}")
    print(f"{'=' * 50}")
    for key, value in sorted(data.items()):
        print(f"  {key:25s}  {value}")
    print(f"{'=' * 50}\n")


if __name__ == "__main__":
    asyncio.run(main())
