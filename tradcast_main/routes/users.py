from fastapi import APIRouter
from storage.firestore_client import firestore_manager
from leaderboard_service import leaderboard_service
from utils.route_utils import handle_streak
from typing import Optional

user_router = APIRouter()


@user_router.get("/home")
async def get_home(fid: str):
    fid_str = str(fid).lower().strip()

    user = await firestore_manager.get_user(fid_str)

    if not user:
        user = await firestore_manager.initiate_user(fid_str)

    streak_updates = await handle_streak(fid_str, user, firestore_manager)
    user.update(streak_updates)
    user["giveaway_eligible"] = None

    return user


@user_router.get("/profile")
async def get_profile(
    fid: str,
    username: Optional[str] = "",
    wallet: Optional[str] = "",
):
    fid_str = str(fid).lower().strip()

    user = await firestore_manager.get_user(fid_str)

    if not user:
        user = await firestore_manager.initiate_user(fid_str, wallet=wallet, username=username)

    streak_updates = await handle_streak(fid_str, user, firestore_manager)
    user.update(streak_updates)

    latest_trades = firestore_manager.get_latest_trades(fid_str, number=4)
    user["latest_trades"] = latest_trades

    return user


@user_router.get("/leaderboard")
async def get_leaderboard(fid: str, top_n: int = 10):
    fid_str = str(fid).lower().strip()

    user = await firestore_manager.get_user(fid_str)
    if not user:
        user = await firestore_manager.initiate_user(fid_str)

    leaderboard = await firestore_manager.get_leaderboard(fid_str, top_n=top_n)

    for entry in leaderboard:
        entry["total_profit"] = int(entry["total_profit"])

    return {"leaderboard": leaderboard}


@user_router.get("/leaderboard/weekly")
async def get_weekly_leaderboard(fid: str, top_n: int = 10):
    fid_str = str(fid).lower().strip()

    leaderboard = leaderboard_service.get_leaderboard(fid_str, "weekly", top_n=top_n)

    for entry in leaderboard:
        entry["weekly_profit"] = int(entry["weekly_profit"])

    return {"leaderboard": leaderboard}


@user_router.get("/leaderboard/daily")
async def get_daily_leaderboard(fid: str, top_n: int = 5):
    fid_str = str(fid).lower().strip()

    leaderboard = leaderboard_service.get_leaderboard(fid_str, "daily", top_n=top_n)

    for entry in leaderboard:
        entry["daily_profit"] = int(entry["daily_profit"])

    return {"leaderboard": leaderboard}


@user_router.get("/leaderboard/monthly")
async def get_monthly_leaderboard(fid: str, top_n: int = 10):
    fid_str = str(fid).lower().strip()

    leaderboard = leaderboard_service.get_leaderboard(fid_str, "monthly", top_n=top_n)

    for entry in leaderboard:
        entry["monthly_profit"] = int(entry["monthly_profit"])

    return {"leaderboard": leaderboard}
