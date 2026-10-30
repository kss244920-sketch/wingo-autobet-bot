#!/usr/bin/env python3
import time
import os
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import telebot
from telebot import types
from typing import Dict, Any, Optional

from config import load_config, save_config
from api_client import WinGoAPIClient
from ai_brain import WinGoAIBrain
from autobet_engine import AutoBetEngine

cfg = load_config()
bot = telebot.TeleBot(cfg["telegram_bot_token"], parse_mode="HTML")

api_client = WinGoAPIClient(site=cfg.get("target_site"), api=cfg.get("target_api"))
ai_brain = WinGoAIBrain(groq_api_key=cfg.get("groq_api_key"))
engine = AutoBetEngine(api_client, ai_brain, cfg)

OWNER_CHAT_ID = int(cfg.get("owner_chat_id", 8327850869))
PINNED_STATUS_MSG_ID: Optional[int] = None
LAST_EDIT_TS = 0.0

def format_status_text(data: Dict[str, Any]) -> str:
    bal = data.get("balance", 100.0)
    start_bal = data.get("start_balance", 100.0)
    target = data.get("target", 500.0)
    wins = data.get("wins", 0)
    losses = data.get("losses", 0)
    skips = data.get("skips", 0)
    cur_issue = data.get("issue", "--")
    last_action = data.get("last_action", "Running...")
    last_settled = data.get("last_settled", "Awaiting first round...")
    is_running = data.get("is_running", False)
    is_demo = data.get("is_demo", True)

    total_settled = wins + losses
    win_rate = f"{(wins / total_settled * 100):.0f}%" if total_settled > 0 else "0%"

    if target > start_bal:
        progress_pct = min(100.0, max(0.0, (bal - start_bal) / (target - start_bal) * 100))
    else:
        progress_pct = min(100.0, max(0.0, (bal / target) * 100)) if target > 0 else 0.0

    bars = int(progress_pct // 10)
    progress_bar = f"[{'█' * bars}{'░' * (10 - bars)}] {progress_pct:.0f}%"

    mode_label = "🟡 <b>DEMO SIMULATION</b>" if is_demo else "🟢 <b>LIVE REAL TRADING</b>"
    engine_state = "🟢 <b>RUNNING (Auto-Trading)</b>" if is_running else "🔴 <b>STOPPED</b>"

    text = (
        f"📌 <b>LIVE WINGO AUTOBET DASHBOARD</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💼 <b>Mode:</b> {mode_label}\n"
        f"⚡ <b>Engine:</b> {engine_state}\n"
        f"🎯 <b>Target Goal:</b> <b>₹{target:,.2f}</b>\n\n"
        f"💰 <b>Current Balance:</b> <b>₹{bal:,.2f}</b> (Start: ₹{start_bal:,.2f})\n"
        f"📈 <b>Goal Progress:</b> {progress_bar}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 <b>Round <code>{cur_issue}</code>:</b>\n{last_action}\n\n"
        f"📜 <b>Last Settled Outcome:</b>\n{last_settled}\n\n"
        f"📊 <b>Scoreboard:</b> {wins}W / {losses}L / {skips} Skips ({win_rate})\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🛡️ <i>Single Live Message · Auto-Updates Every Round</i>"
    )
    return text


def get_dashboard_markup():
    markup = types.InlineKeyboardMarkup(row_width=2)
    b1 = types.InlineKeyboardButton("🚀 Start Auto-Bet", callback_data="cb_start")
    b2 = types.InlineKeyboardButton("🛑 Stop Auto-Bet", callback_data="cb_stop")
    b3 = types.InlineKeyboardButton("🎯 Set Target Goal", callback_data="cb_target")
    b4 = types.InlineKeyboardButton("📜 Trade Audit History", callback_data="cb_history")
    b5 = types.InlineKeyboardButton("🔄 Reset Demo Stats", callback_data="cb_reset")
    b6 = types.InlineKeyboardButton("💼 Refresh Balance", callback_data="cb_balance")
    markup.add(b1, b2)
    markup.add(b3, b4)
    markup.add(b5, b6)
    return markup


def ensure_pinned_status(chat_id: int):
    global PINNED_STATUS_MSG_ID
    
    # First check if there is an existing pinned message from this bot
    if not PINNED_STATUS_MSG_ID:
        try:
            chat_info = bot.get_chat(chat_id)
            pm = getattr(chat_info, "pinned_message", None)
            me = bot.get_me()
            if pm and getattr(pm, "from_user", None) and pm.from_user.id == me.id:
                PINNED_STATUS_MSG_ID = pm.message_id
                print(f"[+] Reusing existing pinned dashboard {PINNED_STATUS_MSG_ID}")
        except Exception:
            pass

    initial_data = {
        "balance": engine.current_balance,
        "start_balance": engine.start_balance,
        "target": engine.target_amount,
        "wins": engine.wins,
        "losses": engine.losses,
        "skips": engine.skips,
        "issue": engine.last_handled_issue or "Initializing...",
        "last_action": engine.last_action_desc,
        "last_settled": engine.last_settled_desc,
        "is_running": engine.is_running,
        "is_demo": engine.is_demo
    }
    text = format_status_text(initial_data)

    if PINNED_STATUS_MSG_ID:
        try:
            bot.edit_message_text(
                text,
                chat_id=chat_id,
                message_id=PINNED_STATUS_MSG_ID,
                reply_markup=get_dashboard_markup()
            )
            return
        except Exception as e:
            if "message is not modified" in str(e).lower():
                return

    # If no existing message or edit failed, send new and pin
    try:
        msg = bot.send_message(chat_id, text, reply_markup=get_dashboard_markup())
        PINNED_STATUS_MSG_ID = msg.message_id
        try:
            bot.pin_chat_message(chat_id, PINNED_STATUS_MSG_ID, disable_notification=True)
            print(f"[+] Pinned dashboard message {PINNED_STATUS_MSG_ID} in chat {chat_id}")
        except Exception as e:
            print(f"[!] Could not pin message: {e}")
    except Exception as e:
        print(f"[!] Could not send dashboard: {e}")


def on_engine_status_update(data: Dict[str, Any]):
    global PINNED_STATUS_MSG_ID, LAST_EDIT_TS
    now = time.time()
    diff = now - LAST_EDIT_TS
    if diff < 1.1:
        time.sleep(1.1 - diff)
    LAST_EDIT_TS = time.time()

    if not OWNER_CHAT_ID:
        return

    text = format_status_text(data)

    if PINNED_STATUS_MSG_ID:
        try:
            bot.edit_message_text(
                text,
                chat_id=OWNER_CHAT_ID,
                message_id=PINNED_STATUS_MSG_ID,
                reply_markup=get_dashboard_markup()
            )
        except Exception as e:
            if "message is not modified" not in str(e).lower():
                print(f"[PINNED EDIT ERROR] {e}")


VIP_CHANNEL_ID = -1003799001380

def parse_channel_signal(raw_text: str) -> Optional[Dict[str, Any]]:
    if not raw_text:
        return None
    clean = re.sub(r"<[^>]+>", " ", raw_text)

    period = None
    pm = re.search(r"Period\s*[:\s]*\.{0,3}(\d+)", clean, re.I)
    if pm:
        period = pm.group(1)

    if "SKIP" in clean.upper():
        return {
            "period": period,
            "decision": "SKIP",
            "confidence": 50.0,
            "strategy": "Capital Guard (Channel SKIP)",
            "time": time.time()
        }

    val = None
    vm = re.search(r"Bet on\s*➔\s*[^A-Z]*(BIG|SMALL)", clean, re.I)
    if vm:
        val = vm.group(1).upper()

    num = None
    nm = re.search(r"Number Chance\s*➔\s*(\d+)", clean, re.I)
    if nm:
        num = int(nm.group(1))

    strat = "30S Predictor VIP Signal"
    sm = re.search(r"Strategy:\s*([^\n\r]+)", clean, re.I)
    if sm:
        strat = sm.group(1).strip()

    if val:
        return {
            "period": period,
            "decision": val,
            "expected_num": num,
            "strategy": strat,
            "confidence": 92.0,
            "time": time.time()
        }
    return None


@bot.channel_post_handler(func=lambda msg: True)
def handle_channel_post(msg):
    if msg.chat.id != VIP_CHANNEL_ID and str(msg.chat.id) != str(VIP_CHANNEL_ID):
        return

    text = msg.text or msg.caption or ""
    parsed = parse_channel_signal(text)
    if parsed:
        ai_brain.set_channel_signal(parsed)
        p = parsed.get("period", "--")
        d = parsed.get("decision", "SKIP")
        strat = parsed.get("strategy", "")
        print(f"📡 [CHANNEL SIGNAL CAPTURED 1:1] Period: {p} | Decision: {d} | Strat: {strat}", flush=True)


def send_trade_history_report(chat_id: int, records: list, start_bal: float, cur_bal: float, target: float):
    if not records:
        bot.send_message(chat_id, "📜 <b>No settled trades recorded in this session yet.</b>")
        return

    wins = sum(1 for r in records if r.get("is_win"))
    losses = sum(1 for r in records if not r.get("is_win"))
    tot = len(records)
    wr = f"{(wins / tot * 100):.1f}%" if tot > 0 else "0%"
    profit = round(cur_bal - start_bal, 2)

    header = (
        f"📊 <b>COMPLETE TRADE AUDIT HISTORY</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Initial Bankroll:</b> ₹{start_bal:,.2f}\n"
        f"💎 <b>Current Balance:</b> <b>₹{cur_bal:,.2f}</b> (Target: ₹{target:,.2f})\n"
        f"📈 <b>Net Profit Generated:</b> <b>{'+' if profit >= 0 else ''}₹{profit:.2f}</b>\n"
        f"🏆 <b>Scoreboard:</b> {wins}W / {losses}L ({wr} Win Rate)\n"
        f"⏱️ <b>Total Trades:</b> {tot} Rounds Executed\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    )

    rows = []
    for idx, r in enumerate(records, 1):
        iss = str(r.get("issue", ""))[-4:]
        choice = r.get("choice", "")
        stake = r.get("stake", 0)
        num = r.get("result_num", 0)
        size = r.get("result_size", "")
        pnl = r.get("pnl", 0)
        bal = r.get("balance", 0)
        badge = "✅ WIN" if r.get("is_win") else "❌ LOSS"
        pnl_str = f"+₹{pnl:.2f}" if pnl >= 0 else f"-₹{abs(pnl):.2f}"
        rows.append(
            f"<b>#{idx}</b> <code>...{iss}</code> | Bet <b>{choice}</b> (₹{stake:.0f}) ➔ Drawn <b>{num} ({size})</b> | {badge} (<b>{pnl_str}</b>) ➔ ₹{bal:.2f}"
        )

    full_text = header + "\n".join(rows) + "\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n🛡️ <i>Live Verified Trades</i>"

    if len(full_text) <= 3800:
        bot.send_message(chat_id, full_text)
    else:
        bot.send_message(chat_id, header)
        chunk = []
        c_len = 0
        for r_str in rows:
            if c_len + len(r_str) > 3500:
                bot.send_message(chat_id, "\n".join(chunk))
                chunk = [r_str]
                c_len = len(r_str)
            else:
                chunk.append(r_str)
                c_len += len(r_str) + 1
        if chunk:
            bot.send_message(chat_id, "\n".join(chunk) + "\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n🛡️ <i>Live Verified Trades</i>")


def on_target_achieved_callback(data: Dict[str, Any]):
    if OWNER_CHAT_ID:
        try:
            records = data.get("history_records", engine.history_records)
            start_bal = data.get("start_balance", engine.start_balance)
            cur_bal = data.get("current_balance", engine.current_balance)
            target = data.get("target", engine.target_amount)
            profit = round(cur_bal - start_bal, 2)

            celebration = (
                f"🎉 <b>TARGET GOAL ACHIEVED: ₹{target:,.2f}!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💰 <b>Starting Balance:</b> ₹{start_bal:,.2f}\n"
                f"💎 <b>Final Balance:</b> <b>₹{cur_bal:,.2f}</b>\n"
                f"📈 <b>Total Net Profit:</b> <b>+₹{profit:,.2f}</b>\n\n"
                f"🛡️ <i>All auto-bets have been safely STOPPED to lock in 100% of profits!</i>"
            )
            bot.send_message(OWNER_CHAT_ID, celebration)
            send_trade_history_report(OWNER_CHAT_ID, records, start_bal, cur_bal, target)
        except Exception as e:
            print(f"[TARGET ACHIEVED ERROR] {e}")


@bot.message_handler(commands=["start", "status"])
def cmd_start(msg):
    global OWNER_CHAT_ID, PINNED_STATUS_MSG_ID
    OWNER_CHAT_ID = msg.chat.id

    initial_data = {
        "balance": engine.current_balance,
        "start_balance": engine.start_balance,
        "target": engine.target_amount,
        "wins": engine.wins,
        "losses": engine.losses,
        "skips": engine.skips,
        "issue": engine.last_handled_issue or "Initializing...",
        "last_action": engine.last_action_desc,
        "last_settled": engine.last_settled_desc,
        "is_running": engine.is_running,
        "is_demo": engine.is_demo
    }
    text = format_status_text(initial_data)
    try:
        sent = bot.reply_to(msg, text, reply_markup=get_dashboard_markup())
        PINNED_STATUS_MSG_ID = sent.message_id
        try:
            bot.pin_chat_message(msg.chat.id, PINNED_STATUS_MSG_ID, disable_notification=True)
        except Exception:
            pass
    except Exception as e:
        print(f"[!] cmd_start error: {e}")


@bot.message_handler(commands=["setamount", "settarget", "target"])
def cmd_setamount(msg):
    parts = msg.text.strip().split()
    if len(parts) < 2 or not parts[1].replace(".", "", 1).isdigit():
        bot.reply_to(msg, "⚠️ <b>Usage:</b> <code>/setamount &lt;target_balance&gt;</code>\nExample: <code>/setamount 500</code>")
        return

    target = float(parts[1])
    engine.set_target(target)
    save_config(engine.config)

    # Immediately edit the single dashboard message
    ensure_pinned_status(msg.chat.id)


@bot.message_handler(commands=["start_betting", "startbet", "run"])
def cmd_start_betting(msg):
    global OWNER_CHAT_ID
    OWNER_CHAT_ID = msg.chat.id

    if engine.is_running:
        bot.reply_to(msg, "ℹ️ Auto-betting engine is already running!")
        return

    started = engine.start(
        on_notification=None,  # NO individual spam notifications!
        on_target_achieved=on_target_achieved_callback,
        on_status_update=on_engine_status_update
    )
    if started:
        ensure_pinned_status(msg.chat.id)


@bot.message_handler(commands=["stop_betting", "stopbet", "pause"])
def cmd_stop_betting(msg):
    if not engine.is_running:
        bot.reply_to(msg, "ℹ️ Engine is not running.")
        return

    engine.stop()
    ensure_pinned_status(msg.chat.id)


@bot.message_handler(commands=["history", "report", "audit"])
def cmd_report(msg):
    send_trade_history_report(msg.chat.id, engine.history_records, engine.start_balance, engine.current_balance, engine.target_amount)


@bot.message_handler(commands=["reset", "resetdemo"])
def cmd_reset(msg):
    engine.current_balance = float(engine.config.get("demo_balance", 100.0))
    engine.start_balance = engine.current_balance
    engine.wins = 0
    engine.losses = 0
    engine.skips = 0
    engine.current_loss_streak = 0
    engine.history_records.clear()
    engine.last_action_desc = "🔄 Demo stats reset to ₹100.00 baseline."
    bot.reply_to(msg, "🔄 <b>Demo balance & scoreboard reset to ₹100.00 baseline!</b>")
    ensure_pinned_status(msg.chat.id)


@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    global OWNER_CHAT_ID
    OWNER_CHAT_ID = chat_id

    data = call.data

    if data == "cb_start":
        if engine.is_running:
            bot.answer_callback_query(call.id, text="⚡ Engine is ALREADY RUNNING live!", show_alert=True)
        else:
            engine.start(
                on_notification=None,
                on_target_achieved=on_target_achieved_callback,
                on_status_update=on_engine_status_update
            )
            bot.answer_callback_query(call.id, text="🚀 Auto-Bet AI Engine Started!", show_alert=False)
            ensure_pinned_status(chat_id)

    elif data == "cb_stop":
        if not engine.is_running:
            bot.answer_callback_query(call.id, text="ℹ️ Engine is already stopped.", show_alert=True)
        else:
            engine.stop()
            bot.answer_callback_query(call.id, text="🛑 Auto-Bet Engine STOPPED. Bets Paused.", show_alert=True)
            ensure_pinned_status(chat_id)

    elif data == "cb_target":
        bot.answer_callback_query(call.id, text=f"🎯 Target Goal: ₹{engine.target_amount:,.2f}\nSend /setamount <amount> to change.", show_alert=True)
        try:
            bot.send_message(chat_id, f"🎯 <b>Current Target:</b> ₹{engine.target_amount:,.2f}\nTo change, type: <code>/setamount 500</code>")
        except Exception:
            pass

    elif data == "cb_balance":
        profit = round(engine.current_balance - engine.start_balance, 2)
        p_sign = "+" if profit >= 0 else ""
        bal_text = (
            f"💰 Balance: ₹{engine.current_balance:,.2f}\n"
            f"🏁 Start: ₹{engine.start_balance:,.2f}\n"
            f"📈 Net PnL: {p_sign}₹{profit:,.2f}\n"
            f"🎯 Target: ₹{engine.target_amount:,.2f}"
        )
        bot.answer_callback_query(call.id, text=bal_text, show_alert=True)
        ensure_pinned_status(chat_id)

    elif data == "cb_status":
        tot = engine.wins + engine.losses
        wr = f"{(engine.wins / tot * 100):.0f}%" if tot > 0 else "0%"
        status_text = (
            f"📊 Engine: {'RUNNING 🟢' if engine.is_running else 'STOPPED 🔴'}\n"
            f"💰 Balance: ₹{engine.current_balance:,.2f}\n"
            f"🏆 Score: {engine.wins}W / {engine.losses}L / {engine.skips} Skips\n"
            f"🎯 Win Rate: {wr}\n"
            f"⚡ Active Round: {engine.last_handled_issue or 'None'}"
        )
        bot.answer_callback_query(call.id, text=status_text, show_alert=True)
        ensure_pinned_status(chat_id)

    elif data == "cb_reset":
        engine.current_balance = float(engine.config.get("demo_balance", 100.0))
        engine.start_balance = engine.current_balance
        engine.wins = 0
        engine.losses = 0
        engine.skips = 0
        engine.current_loss_streak = 0
        engine.history_records.clear()
        engine.last_action_desc = "🔄 Demo stats reset to ₹100.00 baseline."
        bot.answer_callback_query(call.id, text="🔄 Demo balance reset to ₹100.00!", show_alert=True)
        ensure_pinned_status(chat_id)

    elif data == "cb_history":
        bot.answer_callback_query(call.id, text="📜 Loading complete trade audit...")
        send_trade_history_report(chat_id, engine.history_records, engine.start_balance, engine.current_balance, engine.target_amount)

    else:
        bot.answer_callback_query(call.id)


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/backup_and_pin":
            try:
                from audit_cloud_manager import dispatch_and_pin_backup
                res = dispatch_and_pin_backup(trigger_reason="3-Hour Scheduled Restart Checkpoint")
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(res).encode("utf-8"))
                return
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
                return

        if self.path in ("/", "/health", "/panel"):
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            html_content = """<!DOCTYPE html><html><head><title>WinGo AutoBet Engine</title></head>
            <body style='background:#111;color:#0f0;font-family:sans-serif;padding:20px;text-align:center;'>
            <h1>🤖 WinGo AutoBet Quant Engine</h1>
            <p>Status: 🟢 <b>100% HEALTHY & ONLINE</b></p>
            <p>Mode: Free Tier 24/7 Keep-Alive Active</p>
            </body></html>"""
            self.wfile.write(html_content.encode("utf-8"))
            return

        if self.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            data = {
                "bot": "WinGo AutoBet Engine",
                "running": engine.is_running,
                "balance": engine.current_balance,
                "wins": engine.wins,
                "losses": engine.losses,
                "skips": engine.skips,
                "active_issue": engine.last_handled_issue,
                "last_action": engine.last_action_desc,
                "last_settled": engine.last_settled_desc,
                "active_bet": engine.active_bet,
                "mode": "DEMO" if engine.is_demo else "REAL"
            }
            self.wfile.write(json.dumps(data).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        pass


def start_health_server(port=8080):
    try:
        server = HTTPServer(("0.0.0.0", port), HealthHandler)
        print(f"📡 [HEALTH SERVER] Listening on port {port} (200 OK ready) ✅", flush=True)
        server.serve_forever()
    except Exception as e:
        print(f"⚠️ [HEALTH SERVER ERROR] {e}", flush=True)


def main():
    print("=" * 60)
    print("🤖 WinGo Auto-Bet AI Bot Starting (Single-Message Live Mode)...")
    print(f"Token: {cfg.get('telegram_bot_token')[:15]}...")
    print(f"Owner Chat ID: {OWNER_CHAT_ID}")
    print(f"Mode: {'DEMO SIMULATION' if engine.is_demo else 'REAL'}")
    print(f"Balance: ₹{engine.current_balance:.2f} ➔ Target: ₹{engine.target_amount:.2f}")
    print("=" * 60)

    # Start Health Server for Render 24/7 pings
    port = int(os.environ.get("PORT", 8080))
    threading.Thread(target=start_health_server, args=(port,), daemon=True).start()

    # Start Cloud Backup, Silent Pin & Disaster Recovery Daemon
    try:
        from audit_cloud_manager import start_backup_daemon
        start_backup_daemon(interval_seconds=15 * 60)
        print("☁️ [BACKUP DAEMON] Auto Cloud Backup & Pin Daemon active! ✅", flush=True)
    except Exception as e:
        print(f"⚠️ [BACKUP DAEMON] Error: {e}", flush=True)

    if OWNER_CHAT_ID:
        ensure_pinned_status(OWNER_CHAT_ID)
        engine.start(
            on_notification=None,  # No spam messages!
            on_target_achieved=on_target_achieved_callback,
            on_status_update=on_engine_status_update
        )

    bot.infinity_polling(
        timeout=20,
        long_polling_timeout=10,
        allowed_updates=["message", "edited_message", "channel_post", "edited_channel_post", "callback_query"]
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[!] Stopped by user.")
