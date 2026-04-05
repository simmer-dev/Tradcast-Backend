"""Serialize in-memory user cache dicts for JSON responses (datetimes, etc.)."""

from __future__ import annotations

from typing import Any, Dict, Optional


def serialize_for_json(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    iso = getattr(obj, "isoformat", None)
    if callable(iso):
        try:
            return iso()
        except Exception:
            return str(obj)
    if isinstance(obj, dict):
        return {str(k): serialize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [serialize_for_json(v) for v in obj]
    return str(obj)


def export_users_cache(users_cache: Dict[str, dict]) -> Dict[str, Any]:
    return {fid: serialize_for_json(dict(u)) for fid, u in users_cache.items()}


def export_single_user(users_cache: Dict[str, dict], fid: str) -> Optional[dict]:
    fid = str(fid).lower().strip()
    u = users_cache.get(fid)
    if u is None:
        return None
    return serialize_for_json(dict(u))
