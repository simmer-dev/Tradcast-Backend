import os
import json
import asyncio
import random
import string
import requests
from datetime import datetime, date, time, timedelta
from telegram import Bot
from configs.config import TELEGRAM_TOKEN, TELEGRAM_CHANNEL_ID, APP_BASE_URL, ROUND_SECRET


APP_BASE_URL = '' #"https://tradcast.xyz"
ROUND_SECRET = ''
TELEGRAM_BOT_TOKEN = ''
TELEGRAM_CHAT_ID = ''  # channel/group id or @channelusername

ROUND_DURATION_SECONDS = 3 * 60  # 3 minutes
STATE_FILE = "telegram_round_state.json"
# Daily random window (local server time)

WINDOW_START_HOUR = 9    # earliest 09:00
WINDOW_END_HOUR = 23     # latest 23:59

def generate_code(length=6):
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


def trigger_round(code: str):
    headers = {
        "Authorization": f"Bearer {ROUND_SECRET}",
        "Content-Type": "application/json",
    }
    payload = {
        "code": code,
        "durationSeconds": ROUND_DURATION_SECONDS,
    }
    res = requests.post(
        f"{APP_BASE_URL}/api/start-round",
        json=payload,
        headers=headers,
        timeout=15,
    )
    res.raise_for_status()
    return res.json()


def load_state():
    if not os.path.exists(STATE_FILE):
        return {"last_run_date": None}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"last_run_date": None}


def save_state(last_run_date: str):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"last_run_date": last_run_date}, f)


def pick_random_time_for_day(target_day: date) -> datetime:
    start_dt = datetime.combine(target_day, time(hour=WINDOW_START_HOUR, minute=0, second=0))
    end_dt = datetime.combine(target_day, time(hour=WINDOW_END_HOUR, minute=59, second=59))
    total_seconds = int((end_dt - start_dt).total_seconds())
    offset = random.randint(0, max(total_seconds, 1))
    return start_dt + timedelta(seconds=offset)


async def run_daily_random_round():
    bot = Bot(token=TELEGRAM_TOKEN)
    state = load_state()
    while True:
        today = date.today()
        today_str = today.isoformat()
        # If already ran today, schedule tomorrow
        if state.get("last_run_date") == today_str:
            target_day = today + timedelta(days=1)
        else:
            target_day = today
        target_dt = pick_random_time_for_day(target_day)
        now = datetime.now()
        # if selected time already passed today, move to tomorrow

        if target_dt <= now:
            target_dt = pick_random_time_for_day(today + timedelta(days=1))

        sleep_seconds = (target_dt - now).total_seconds()
        print(f"[scheduler] Next round at {target_dt.isoformat()} (in {int(sleep_seconds)}s)")
        await asyncio.sleep(max(1, int(sleep_seconds)))
        # re-check guard to avoid duplicate if state changed
        current_date_str = date.today().isoformat()
        state = load_state()

        if state.get("last_run_date") == current_date_str:
            continue

        code = generate_code(6)
        data = await asyncio.to_thread(trigger_round, code)
        await bot.send_message(
            chat_id=TELEGRAM_CHANNEL_ID,
            text=(
                "🔥 New Tradcast code is live!\n"
                f"Code: {code}\n"
                "⏱ Valid for 3 minutes\n"
                "🏁 First 5 unique wallets win USD prize"
            ),
        )
        print("Round started:", data)
        save_state(current_date_str)
        state["last_run_date"] = current_date_str

if __name__ == "__main__":
    asyncio.run(run_daily_random_round())

