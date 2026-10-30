#!/usr/bin/env python3
"""
Render 24/7 Zero-Sleep Keep-Alive & Auto-Healer for WinGo AutoBet Quant Engine.
Pings the Render web service URL every 4 minutes to bypass Render's 15-minute inactivity spin-down.
If the service is down or unhealthy, automatically uses the Render REST API to restart it.
"""

import os
import sys
import json
import time
import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    print("requests library not found. Please install requests.")
    sys.exit(1)

BASE_DIR = Path(__file__).parent.parent.resolve()
CONFIG_FILE = BASE_DIR / "render_config.json"
LOG_FILE = BASE_DIR / "keep_alive_render.log"


def log(msg):
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{now_str}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_config():
    cfg = {}
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception as e:
            log(f"Error loading {CONFIG_FILE}: {e}")

    api_key = os.environ.get("RENDER_API_KEY") or cfg.get("api_key")
    owner_id = os.environ.get("RENDER_OWNER_ID") or cfg.get("owner_id")
    service_id = os.environ.get("RENDER_SERVICE_ID") or cfg.get("service_id")
    service_url = os.environ.get("RENDER_SERVICE_URL") or cfg.get("service_url")
    service_name = os.environ.get("RENDER_SERVICE_NAME") or cfg.get("service_name") or "wingo-autobet-bot"

    return {
        "api_key": api_key,
        "owner_id": owner_id,
        "service_id": service_id,
        "service_url": service_url,
        "service_name": service_name,
    }


def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        log(f"Error saving config: {e}")


def restart_service(api_key, service_id):
    """Triggers restart via Render REST API."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json"
    }
    url = f"https://api.render.com/v1/services/{service_id}/restart"
    try:
        r = requests.post(url, headers=headers, timeout=20)
        if r.status_code in (200, 201, 202):
            log(f"🔄 Successfully requested restart for service {service_id}")
            return True
        else:
            log(f"Restart failed with status {r.status_code}: {r.text}")
    except Exception as e:
        log(f"Restart request exception: {e}")
    return False


def ping_once():
    log("Running Render 24/7 Keep-Alive & Health Ping Check...")
    cfg = load_config()
    api_key = cfg.get("api_key")
    service_id = cfg.get("service_id")
    service_url = cfg.get("service_url")

    if not service_url:
        log("Notice: No active Render service URL configured.")
        return False

    ping_url = service_url.rstrip("/") + "/"
    log(f"📡 Sending Keep-Alive Ping to: {ping_url}")
    for attempt in range(1, 4):
        try:
            r = requests.get(ping_url, timeout=25)
            if r.status_code == 200:
                log(f"✅ Service is 100% HEALTHY & ALIVE! (HTTP {r.status_code}) - Inactivity timer reset.")
                return True
            else:
                log(f"⚠️ Health ping attempt {attempt} returned unexpected status: {r.status_code}")
        except requests.exceptions.RequestException as e:
            log(f"⚠️ Ping attempt {attempt} failed: {e}")
        if attempt < 3:
            time.sleep(3)

    if service_id and api_key:
        log("Attempting automatic service revival via Render API restart...")
        restart_service(api_key, service_id)
    return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Render 24/7 Keep-Alive & Auto-Healer")
    parser.add_argument("--loop", type=int, default=0, help="Run continuously for N minutes (pings every 4 mins)")
    parser.add_argument("--interval", type=int, default=240, help="Interval between pings in seconds (default 240)")
    args = parser.parse_args()

    if args.loop <= 0:
        ping_once()
        return

    end_time = time.time() + (args.loop * 60)
    log(f"🚀 Starting continuous Keep-Alive loop for {args.loop} minutes (ping interval: {args.interval}s)...")
    while time.time() < end_time:
        ping_once()
        remaining = end_time - time.time()
        if remaining <= 0:
            break
        sleep_dur = min(args.interval, remaining)
        time.sleep(sleep_dur)
    log("🏁 Continuous keep-alive session ended.")


if __name__ == "__main__":
    main()
