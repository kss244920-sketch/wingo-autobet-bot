import os
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "bot_config.json")

DEFAULT_CONFIG = {
    "telegram_bot_token": os.environ.get("TELEGRAM_BOT_TOKEN", "8751111148:AAH9k6fOYw5LW9pIzN3-8jCddcR96s0_-bU"),
    "groq_api_key": os.environ.get("GROQ_API_KEY", ""),
    "owner_chat_id": 8327850869,
    "target_site": "https://www.dmfirst17.com",
    "target_api": "https://api.dmfirst9api.com",
    
    # Mode switch for fast testing: 30 Seconds
    "game_type_id": 30,             # WinGo 30s
    "game_code": "WinGo_30S",
    "history_api_url": "https://draw.ar-lottery01.com/WinGo/WinGo_30S/GetHistoryIssuePage.json",
    
    # Demo Simulation Settings
    "demo_mode": True,
    "demo_balance": 100.0,
    "target_amount": 500.0,
    "stop_loss_amount": 25.0,
    
    # Quality & Risk Settings
    "min_confidence_to_bet": 80.0,
    "min_quant_margin_pct": 14.0,
    "prefer_skips": True,           # Strictly prefer automatic skips
    "base_stake_pct": 0.10,         # 10% dynamic stake for swift target compounding
    "min_stake": 5,
    "max_stake_cap": 85,
    "max_loss_streak_halt": 3,
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                cfg = dict(DEFAULT_CONFIG)
                cfg.update(data)
                return cfg
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)

def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print(f"[CONFIG ERROR] Failed to save config: {e}")
