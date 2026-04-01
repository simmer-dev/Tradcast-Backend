import subprocess
import time
from datetime import datetime
import sys
from mail_handler import *
import threading

# ────────────────────────────────────────────────
# CONFIGURATION – change only here
# ────────────────────────────────────────────────
TARGETS = {
    "Default":      "193.111.78.244",
    "South Africa": "54.94.146.30",
    "West Africa":  "176.97.192.92",
}

HOSTNAME      = "api.tradcast.xyz"
URL_PATH      = "/health"
EXPECTED_TEXT = '{"status":"healthy"}'
TIMEOUT_SEC   = 15
INTERVAL_MIN  = 1

# ────────────────────────────────────────────────
# Alert function – customize this
# ────────────────────────────────────────────────
def alert(region: str, ip: str, reason: str = ""):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg = f"[{now}] {region:<14} ({ip}) DOWN – {reason}"
    print(msg, file=sys.stderr)
    send_mail(subject='Server Down', body=msg)
    # send_email_to_myself("Server DOWN", msg)  # ← add your real alert here

def send_alive():
    while True:
        time.sleep(12*60*60)
        send_mail('server message', 'i am alive')
# ────────────────────────────────────────────────
# Check one server using curl --resolve
# ────────────────────────────────────────────────
def check_server(region: str, ip: str):
    url = f"https://{HOSTNAME}{URL_PATH}"

    cmd = [
        "curl",
        "--silent",
        "--show-error",
        "--max-time", str(TIMEOUT_SEC),
        "--resolve", f"{HOSTNAME}:443:{ip}",
        "--write-out", "\n%{http_code} %{time_total}",
        url,
    ]

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SEC + 5,  # slightly longer than curl's own timeout
        )

        output = result.stdout.strip()
        stderr = result.stderr.strip()

        # Last line is our --write-out stats; everything before is the body
        *body_lines, stats_line = output.splitlines()
        body = "\n".join(body_lines).strip()

        parts      = stats_line.split()
        http_code  = parts[0] if parts else "???"
        time_total = float(parts[1]) if len(parts) > 1 else 0.0

        if result.returncode != 0:
            reason = stderr or f"curl exit code {result.returncode}"
            print(f"[{now}] {region:<14} ({ip}) ERROR   {time_total:.3f}s  – {reason}")
            alert(region, ip, reason)
            return False

        if http_code == "200" and body == EXPECTED_TEXT:
            print(f"[{now}] {region:<14} ({ip}) OK      {time_total:.3f}s")
            return True
        else:
            reason = f"HTTP {http_code} – {body!r}"
            print(f"[{now}] {region:<14} ({ip}) BAD     {time_total:.3f}s  – {reason}")
            alert(region, ip, reason)
            return False

    except subprocess.TimeoutExpired:
        reason = f"timed out after {TIMEOUT_SEC}s"
        print(f"[{now}] {region:<14} ({ip}) TIMEOUT – {reason}")
        alert(region, ip, reason)
        return False

    except Exception as e:
        print(f"[{now}] {region:<14} ({ip}) CRASH   – {e}")
        alert(region, ip, str(e))
        return False

# ────────────────────────────────────────────────
# Main loop
# ────────────────────────────────────────────────
def main():
    print("Geo Health Monitor started")
    print(f"Interval : {INTERVAL_MIN} min | Timeout: {TIMEOUT_SEC}s")
    print(f"Targets  : {', '.join(TARGETS.keys())}")
    print("-" * 70)

    while True:
        for region, ip in TARGETS.items():
            check_server(region, ip)

        print("-" * 70)
        time.sleep(INTERVAL_MIN * 60)

if __name__ == "__main__":
    try:
        threading.Thread(target=send_alive, daemon=True).start()
        main()
    except KeyboardInterrupt:
        print("\nStopped by user.")
    except Exception as e:
        print(f"Monitor crashed: {e}", file=sys.stderr)
