"""Fetch user energy from tradcast_main's in-memory cache (server-to-server)."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Optional

import requests

if TYPE_CHECKING:
    from storage.firestore_client import FirestoreManager


async def fetch_energy_from_main(main_api_url: str, secret: str, fid: str) -> Optional[int]:
    """Return energy from main's _users_cache, or None if the request failed."""
    fid = str(fid).lower().strip()
    base = main_api_url.rstrip("/")
    try:
        r = await asyncio.to_thread(
            requests.get,
            f"{base}/internal/user_energy",
            params={"fid": fid, "secret": secret},
            timeout=10,
        )
    except Exception:
        return None
    if r.status_code == 200:
        try:
            return int(r.json().get("energy", 0))
        except (TypeError, ValueError):
            return None
    if r.status_code == 404:
        try:
            return int(r.json().get("energy", 0))
        except (TypeError, ValueError):
            return 0
    return None


async def sync_game_cache_energy_from_main(
    fm: "FirestoreManager",
    main_api_url: str,
    secret: str,
    fid: str,
) -> bool:
    """
    Copy main server's cached energy into this process's user cache.
    If the user row is missing locally, loads it from Firestore once via get_user.
    Returns False if the main request failed (caller should use local cache only).
    """
    fid = str(fid).lower().strip()
    e = await fetch_energy_from_main(main_api_url, secret, fid)
    if e is None:
        return False
    user = fm._users_cache.get(fid)
    if user is None:
        loaded = await fm.get_user(fid)
        if loaded is None:
            return False
        user = fm._users_cache.get(fid)
        if user is None:
            return False
    user["energy"] = e
    return True
