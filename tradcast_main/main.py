import sys, os
_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_dir))
sys.path.insert(0, _dir)

import asyncio
import json
import time as _time
from datetime import datetime, timezone
from typing import Dict
from pathlib import Path
from collections import defaultdict
from threading import Lock

from fastapi import FastAPI, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import Response as StarletteResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from routes.users import user_router
from routes.sessions import session_router
from configs.config import CORS_ALLOWED_ORIGINS, SECRET
from utils.cache_export import export_single_user, export_users_cache
from htmls import not_found_html
from storage.firestore_client import firestore_manager, firestore_read_counter
from storage.local_trades_db import trades_db
from storage.energy_manager import EnergyManager
from leaderboard_service import leaderboard_service

energy_manager = EnergyManager(firestore_manager)

DEBUG = True

app = FastAPI()

# ====================== Debug stats ======================
_stats_lock = Lock()
_stats = {
    "start_time": _time.time(),
    "http_requests_total": 0,
    "http_requests_by_path": defaultdict(int),
    "score_updates_received": 0,
    "score_updates_rejected": 0,
    "energy_lookups_received": 0,
    "energy_lookups_rejected": 0,
}


ALLOWED_PATH_PREFIXES = (
    "/",
    "/docs",
    "/openapi.json",
    "/health",
    "/ws",
    "/api/v1/session",
    "/api/v1/user",
    "/internal/",
    "/debug",
    "/favicon.ico",
    "/static/",
)


class BlockUnknownRoutesMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        if any(path.startswith(prefix) for prefix in ALLOWED_PATH_PREFIXES):
            await self.app(scope, receive, send)
            return

        response = StarletteResponse(content=not_found_html, status_code=403, media_type="text/html")
        await response(scope, receive, send)


app.add_middleware(CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(BlockUnknownRoutesMiddleware)


# ====================== Include Routers ======================
app.include_router(session_router, prefix="/api/v1/session", tags=["session"])
app.include_router(user_router, prefix="/api/v1/user", tags=["user"])


@app.get("/")
async def root():
    return {"message": "Miniapp backend is running"}


@app.get("/health")
async def health():
    return {"status": "ok"}


# ====================== Debug request counter middleware ======================

@app.middleware("http")
async def debug_request_counter(request: Request, call_next):
    if DEBUG:
        path = request.url.path
        with _stats_lock:
            _stats["http_requests_total"] += 1
            _stats["http_requests_by_path"][path] += 1
    return await call_next(request)


@app.get("/debug")
async def debug_info():
    if not DEBUG:
        return {"debug": False}

    uptime = _time.time() - _stats["start_time"]
    lb_scores = leaderboard_service._scores

    with _stats_lock:
        requests_by_path = dict(_stats["http_requests_by_path"])
        snapshot = {
            "http_requests_total": _stats["http_requests_total"],
            "score_updates_received": _stats["score_updates_received"],
            "score_updates_rejected": _stats["score_updates_rejected"],
            "energy_lookups_received": _stats["energy_lookups_received"],
            "energy_lookups_rejected": _stats["energy_lookups_rejected"],
        }

    return {
        "server": "tradcast_main",
        "debug": True,
        "uptime_seconds": round(uptime, 1),
        "uptime_human": f"{int(uptime // 3600)}h {int((uptime % 3600) // 60)}m {int(uptime % 60)}s",
        "leaderboard_cache": {
            "users_in_memory": len(lb_scores),
            "periods_tracked": list(leaderboard_service.PERIODS),
        },
        "gameplay_tracker": {
            "fids_tracked": len(gameplay_tracker.gameplay_data),
            "users_map_size": len(gameplay_tracker.users_map),
        },
        "http": {
            "total_requests": snapshot["http_requests_total"],
            "requests_by_path": dict(sorted(requests_by_path.items(), key=lambda x: x[1], reverse=True)),
        },
        "score_sync": {
            "updates_received": snapshot["score_updates_received"],
            "updates_rejected": snapshot["score_updates_rejected"],
            "energy_lookups_received": snapshot["energy_lookups_received"],
            "energy_lookups_rejected": snapshot["energy_lookups_rejected"],
        },
        "trades_db": {
            "rows": trades_db.count(),
            "max_rows": 10000,
        },
        "firestore": {
            "keep_alive_started": firestore_manager._keep_alive_started,
            "users_cache_size": len(firestore_manager._users_cache),
            "reads": firestore_read_counter.snapshot(),
        },
    }


# ====================== Internal endpoint for game server sync ======================

@app.post("/internal/update_score")
async def internal_update_score(request: Request):
    """Receive score + trade summary from game servers, update cache + local SQLite."""
    data = await request.json()
    if data.get("secret") != SECRET:
        if DEBUG:
            with _stats_lock:
                _stats["score_updates_rejected"] += 1
            print(f"[DEBUG] score update REJECTED (bad secret) from {request.client.host}")
        return JSONResponse(status_code=403, content={"error": "forbidden"})
    fid = str(data["fid"]).lower().strip()
    profit = data["profit"]
    final_pnl = data.get("final_pnl", 0.0)
    leaderboard_service.update_cache(fid, profit)

    user = firestore_manager._users_cache.get(fid)
    if user is not None:
        old_tp = user.get("total_profit", 0)
        user["total_profit"] = old_tp + profit
        user["total_PnL"] = user.get("total_PnL", 0) + final_pnl
        user["total_games"] = user.get("total_games", 0) + 1
        user["energy"] = max(0, user.get("energy", 0) - 1)
        user["daily_games"] = user.get("daily_games", 0) + 1
        user["last_online"] = datetime.now(timezone.utc)
        firestore_manager._lb_cache.clear()
        if DEBUG:
            print(
                f"[DEBUG] cache updated  fid={fid}  "
                f"total_profit: {old_tp:.2f} -> {user['total_profit']:.2f}  "
                f"energy={user.get('energy')}  daily_games={user.get('daily_games')}"
            )
    else:
        if DEBUG:
            print(f"[DEBUG] fid NOT in cache  fid={fid}  cache_size={len(firestore_manager._users_cache)}")

    session_id = data.get("session_id")
    if session_id:
        trades_db.insert_trade_summary(
            session_id=session_id,
            fid=fid,
            trade_env_id=data.get("trade_env_id", ""),
            final_pnl=data.get("final_pnl", 0.0),
            final_profit=profit,
            created_at=data.get("created_at", 0.0),
        )

    if DEBUG:
        with _stats_lock:
            _stats["score_updates_received"] += 1
        cache_size = len(leaderboard_service._scores)
        db_size = trades_db.count()
        print(
            f"[DEBUG] score update RECEIVED  fid={fid}  profit={profit:.2f}  "
            f"leaderboard_cache={cache_size} users  trades_db={db_size} rows"
        )
    return {"status": "ok"}


@app.get("/internal/user_energy")
async def internal_user_energy(
    fid: str = Query(...),
    secret: str = Query(...),
):
    """Game servers: read energy from main's in-memory user cache (same source as the app)."""
    if secret != SECRET:
        if DEBUG:
            with _stats_lock:
                _stats["energy_lookups_rejected"] += 1
            print(f"[DEBUG] energy lookup REJECTED (bad secret)")
        return JSONResponse(status_code=403, content={"error": "forbidden"})
    fid = str(fid).lower().strip()
    if DEBUG:
        with _stats_lock:
            _stats["energy_lookups_received"] += 1
    user = firestore_manager._users_cache.get(fid)
    if user is None:
        return JSONResponse(
            status_code=404,
            content={"error": "unknown_fid", "energy": 0},
        )
    try:
        energy = int(user.get("energy", 0) or 0)
    except (TypeError, ValueError):
        energy = 0
    return {"fid": fid, "energy": energy}


@app.get("/internal/users_cache")
async def internal_users_cache(secret: str = Query(...)):
    """Full in-memory users cache (JSON-safe). Large response — use sparingly."""
    if secret != SECRET:
        return JSONResponse(status_code=403, content={"error": "forbidden"})
    data = export_users_cache(firestore_manager._users_cache)
    return {
        "count": len(data),
        "users": data,
    }


@app.get("/internal/user_cache")
async def internal_user_cache(
    fid: str = Query(...),
    secret: str = Query(...),
):
    """Single user document from main's in-memory users cache."""
    if secret != SECRET:
        return JSONResponse(status_code=403, content={"error": "forbidden"})
    fid = str(fid).lower().strip()
    user = export_single_user(firestore_manager._users_cache, fid)
    if user is None:
        return JSONResponse(
            status_code=404,
            content={"error": "unknown_fid", "fid": fid},
        )
    return {"fid": fid, "user": user}


# ====================== Gameplay Tracker ======================

class DailyGameplayTracker:
    """Tracks daily gameplay counts per FID with UTC midnight resets and persistent storage"""

    def __init__(self, storage_file: str = "gameplay_data.json", users_file: str = "users.json"):
        self.storage_file = storage_file
        self.users_file = users_file
        self.gameplay_data: Dict[str, Dict] = {}
        self.users_map: Dict[str, str] = {}
        self._load_from_disk()
        self._load_users()

    def _load_from_disk(self):
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, 'r') as f:
                    self.gameplay_data = json.load(f)
                print(f"Loaded gameplay data from {self.storage_file}")
            except Exception as e:
                print(f"Error loading gameplay data: {e}")
                self.gameplay_data = {}
        else:
            print(f"No existing gameplay data found, starting fresh")
            self.gameplay_data = {}

    def _load_users(self):
        if os.path.exists(self.users_file):
            try:
                with open(self.users_file, 'r') as f:
                    users_list = json.load(f)
                    self.users_map = {}
                    for user_obj in users_list:
                        for fid, username in user_obj.items():
                            self.users_map[fid] = username
                print(f"Loaded {len(self.users_map)} users from {self.users_file}")
            except Exception as e:
                print(f"Error loading users data: {e}")
                self.users_map = {}
        else:
            print(f"No users.json found")
            self.users_map = {}

    def _save_to_disk(self):
        try:
            Path(self.storage_file).parent.mkdir(parents=True, exist_ok=True)
            with open(self.storage_file, 'w') as f:
                json.dump(self.gameplay_data, f, indent=2)
        except Exception as e:
            print(f"Error saving gameplay data: {e}")

    def get_current_utc_date(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def increment_gameplay(self, fid: str, amount: int = 2) -> int:
        current_date = self.get_current_utc_date()
        if fid not in self.gameplay_data:
            self.gameplay_data[fid] = {"count": amount, "date": current_date}
        else:
            if self.gameplay_data[fid]["date"] != current_date:
                self.gameplay_data[fid] = {"count": amount, "date": current_date}
            else:
                self.gameplay_data[fid]["count"] += amount
        self._save_to_disk()
        return self.gameplay_data[fid]["count"]

    def get_gameplay_count(self, fid: str) -> int:
        current_date = self.get_current_utc_date()
        if fid not in self.gameplay_data:
            return 0
        if self.gameplay_data[fid]["date"] != current_date:
            return 0
        return self.gameplay_data[fid]["count"]

    def get_gameplay_data_with_usernames(self) -> Dict[str, Dict]:
        result = {}
        for fid, data in self.gameplay_data.items():
            username = self.users_map.get(fid, f"Unknown_{fid}")
            result[username] = {"count": data["count"], "date": data["date"]}
        return result

    def reset_all(self):
        self.gameplay_data.clear()
        self._save_to_disk()

    def cleanup_old_data(self, days_to_keep: int = 7):
        current_date = datetime.now(timezone.utc)
        fids_to_remove = []
        for fid, data in self.gameplay_data.items():
            data_date = datetime.strptime(data["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if (current_date - data_date).days > days_to_keep:
                fids_to_remove.append(fid)
        for fid in fids_to_remove:
            del self.gameplay_data[fid]
        if fids_to_remove:
            self._save_to_disk()
            print(f"Cleaned up {len(fids_to_remove)} old entries")


gameplay_tracker = DailyGameplayTracker()


@app.get("/increase_tracker")
async def increase_tracker(fid):
    current_gameplay = gameplay_tracker.increment_gameplay(str(fid), amount=2)
    return {"status": "ok"}


@app.get("/get_tracker")
async def get_tracker():
    """Get gameplay data with usernames instead of FIDs"""
    return gameplay_tracker.get_gameplay_data_with_usernames()


@app.on_event("startup")
async def warm_up_firestore():
    try:
        await firestore_manager.db.collection("_warmup").document("_ping").get()
        firestore_read_counter.inc("startup_warmup")
        print("Firestore gRPC channel warmed up")
    except Exception as e:
        print(f"Firestore warmup error (non-fatal): {e}")

    await firestore_manager.load_all_users()
    await firestore_manager.start_keep_alive()

    await leaderboard_service.load()
    leaderboard_service.start_reset_loop()

    asyncio.create_task(energy_manager.start_reenergization_loop())

    if DEBUG:
        print(
            f"[DEBUG] tradcast_main ready  "
            f"users_cache={len(firestore_manager._users_cache)}  "
            f"leaderboard_cache={len(leaderboard_service._scores)} users  "
            f"gameplay_tracker={len(gameplay_tracker.gameplay_data)} fids"
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        port=6001,
    )
