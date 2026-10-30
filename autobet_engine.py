import time
import math
import threading
from typing import Dict, Any, Optional, Callable
from api_client import WinGoAPIClient
from ai_brain import WinGoAIBrain

class AutoBetEngine:
    def __init__(self, api_client: WinGoAPIClient, ai_brain: WinGoAIBrain, config: Dict[str, Any]):
        self.api = api_client
        self.brain = ai_brain
        self.config = config

        self.is_running = False
        self.thread: Optional[threading.Thread] = None

        # Demo vs Real Mode
        self.is_demo: bool = bool(config.get("demo_mode", True))
        self.start_balance: float = float(config.get("demo_balance", 100.0)) if self.is_demo else 0.0
        self.current_balance: float = self.start_balance
        self.target_amount: float = float(config.get("target_amount", 500.0))
        self.stop_loss_amount: float = float(config.get("stop_loss_amount", 25.0))

        # Metrics
        self.current_loss_streak: int = 0
        self.total_bets_placed: int = 0
        self.wins: int = 0
        self.losses: int = 0
        self.skips: int = 0
        self.history_records: list = []

        # Current Round Tracker
        self.last_handled_issue: Optional[str] = None
        self.active_bet: Optional[Dict[str, Any]] = None
        self.last_action_desc: str = "Initializing AI Models..."
        self.last_settled_desc: str = "Awaiting first round..."

        # Callbacks
        self.on_notification: Optional[Callable[[str], None]] = None
        self.on_target_achieved: Optional[Callable[[Dict[str, Any]], None]] = None
        self.on_status_update: Optional[Callable[[Dict[str, Any]], None]] = None

    def set_target(self, target_amount: float):
        self.target_amount = float(target_amount)
        self.config["target_amount"] = self.target_amount

    def set_stop_loss(self, stop_loss_amount: float):
        self.stop_loss_amount = float(stop_loss_amount)
        self.config["stop_loss_amount"] = self.stop_loss_amount

    def calculate_stake(self, confidence: float = 80.0, strategy: str = "") -> int:
        bal = self.current_balance if self.current_balance > 0 else 100.0

        # Autonomous AI Dynamic Sizing:
        # High Conviction (88%+ or confirmed Roadmap/Dragon): 12% - 15% of bankroll for rapid compounding
        # Strong Conviction (80% - 87%): 8% - 10% of bankroll
        # Standard Conviction (70% - 79%): 5% - 6% of bankroll
        strat_upper = strategy.upper()
        if confidence >= 88.0 or "ROADMAP" in strat_upper or "DRAGON" in strat_upper:
            pct = 0.12
        elif confidence >= 80.0:
            pct = 0.08
        else:
            pct = 0.05

        base_calc = max(int(self.config.get("min_stake", 3)), int(round(bal * pct)))

        # Anti-Martingale & Capital Protection:
        # After a loss, DO NOT double down into chaos!
        if self.current_loss_streak == 1:
            # Gentle 1.3X only if confidence is very high, else base stake
            mult = 1.3 if confidence >= 90.0 else 1.0
            stake = max(base_calc, int(round(base_calc * mult)))
        elif self.current_loss_streak >= 2:
            # Capital Defense: Shrink stake to minimum base to weather drawdowns
            stake = max(int(self.config.get("min_stake", 3)), int(round(bal * 0.04)))
        else:
            stake = base_calc

        # Safety cap: Never risk more than 28% of bankroll in any single round
        max_allowed = max(5, int(round(bal * 0.28)))
        stake = min(stake, max_allowed)

        # Target Clamping: If close to target, only bet what is needed to hit the goal!
        if self.target_amount > bal:
            needed = int(math.ceil((self.target_amount - bal) / 0.96))
            stake = min(stake, max(3, needed))

        return max(1, stake)

    def start(self, on_notification: Optional[Callable[[str], None]] = None,
              on_target_achieved: Optional[Callable[[Dict[str, Any]], None]] = None,
              on_status_update: Optional[Callable[[Dict[str, Any]], None]] = None) -> bool:
        if self.is_running:
            return False

        if not self.is_demo:
            self.current_balance = self.api.fetch_balance()
            self.start_balance = self.current_balance
        else:
            self.start_balance = float(self.config.get("demo_balance", 100.0))
            self.current_balance = self.start_balance

        self.is_running = True
        self.on_notification = on_notification
        self.on_target_achieved = on_target_achieved
        self.on_status_update = on_status_update

        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        return True

    def stop(self):
        self.is_running = False

    def _notify(self, msg: str):
        if self.on_notification:
            try:
                self.on_notification(msg)
            except Exception as e:
                print(f"[NOTIFY ERROR] {e}")

    def _update_status(self, cur_issue: str):
        if self.on_status_update:
            try:
                self.on_status_update({
                    "issue": cur_issue,
                    "balance": self.current_balance,
                    "start_balance": self.start_balance,
                    "target": self.target_amount,
                    "wins": self.wins,
                    "losses": self.losses,
                    "skips": self.skips,
                    "loss_streak": self.current_loss_streak,
                    "last_action": self.last_action_desc,
                    "last_settled": self.last_settled_desc,
                    "is_running": self.is_running,
                    "is_demo": self.is_demo,
                    "active_bet": self.active_bet
                })
            except Exception as e:
                print(f"[STATUS UPDATE ERROR] {e}")

    def _run_loop(self):
        print(f"[+] WinGo ({self.config.get('game_code', 'WinGo_30S')}) Engine Running (Single-Message Live Mode).", flush=True)

        history_url = self.config.get("history_api_url", "https://draw.ar-lottery01.com/WinGo/WinGo_30S/GetHistoryIssuePage.json")
        game_type_id = int(self.config.get("game_type_id", 30))

        while self.is_running:
            try:
                # 1. Fetch current issue from history or API
                history = self.api.get_history(history_url)
                if not history:
                    time.sleep(2)
                    continue

                latest_settled = history[-1] if history else {}
                latest_issue = str(latest_settled.get("issueNumber", ""))
                
                try:
                    cur_issue = str(int(latest_issue) + 1)
                except Exception:
                    cur_issue = latest_issue

                # Check if this is a new round
                if cur_issue != self.last_handled_issue:
                    # 1. Check resolution of previously active bet
                    if self.active_bet and self.last_handled_issue:
                        self._resolve_previous_bet(self.active_bet["issue"], history)
                        self.last_action_desc = "🧠 <i>AI analyzing market trends for next round...</i>"
                        self._update_status(cur_issue)
                        # Brief pause so the user sees the win/loss settlement on the pinned dashboard
                        time.sleep(2.0)

                    self.last_handled_issue = cur_issue
                    self.active_bet = None

                    # 🎯 2. TARGET CHECK: Has target balance been achieved?
                    if self.target_amount > 0 and self.current_balance >= self.target_amount:
                        profit = round(self.current_balance - self.start_balance, 2)
                        achieved_msg = (
                            f"🎉 <b>TARGET BALANCE ACHIEVED!</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━\n"
                            f"🎯 <b>Target:</b> ₹{self.target_amount:,.2f}\n"
                            f"💰 <b>Final Balance:</b> ₹{self.current_balance:,.2f}\n"
                            f"📈 <b>Net Profit:</b> +₹{profit:,.2f}\n"
                            f"🛡️ <b>Safety Guard:</b> Auto-betting safely stopped to lock in profits!"
                        )
                        self.last_action_desc = f"🎯 TARGET ACHIEVED (₹{self.current_balance:.2f} / ₹{self.target_amount:.2f})"
                        self._update_status(cur_issue)
                        self._notify(achieved_msg)
                        if self.on_target_achieved:
                            self.on_target_achieved({
                                "start_balance": self.start_balance,
                                "current_balance": self.current_balance,
                                "target": self.target_amount,
                                "profit": profit
                            })
                        self.is_running = False
                        break

                    # 🛑 3. STOP-LOSS CHECK
                    if self.stop_loss_amount > 0 and self.current_balance <= self.stop_loss_amount:
                        loss_msg = (
                            f"🛑 <b>STOP-LOSS TRIGGERED</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━\n"
                            f"⚠️ Balance (₹{self.current_balance:.2f}) reached floor limit (₹{self.stop_loss_amount:.2f}).\n"
                            f"Auto-betting stopped to protect remaining capital."
                        )
                        self.last_action_desc = f"🛑 STOP-LOSS HIT (₹{self.current_balance:.2f})"
                        self._update_status(cur_issue)
                        self._notify(loss_msg)
                        self.is_running = False
                        break

                    # 🧠 4. Run Deep AI Thinking & Quant Analysis (Synchronized with 30S Predictor Stream)
                    analysis = self.brain.analyze(history, current_loss_streak=self.current_loss_streak, target_issue=cur_issue)
                    decision = analysis.get("decision", "SKIP")
                    confidence = analysis.get("confidence", 50.0)
                    strategy = analysis.get("strategy", "")
                    reason = analysis.get("reason", "")
                    is_qualified = analysis.get("is_qualified", False)
                    expected_nums = analysis.get("expected_nums")

                    # 5. Action Execution (SINGLE MESSAGE UPDATE ONLY)
                    if is_qualified and decision in ("BIG", "SMALL"):
                        stake = self.calculate_stake(confidence=confidence, strategy=strategy)
                        
                        if self.is_demo:
                            self.current_balance = round(self.current_balance - stake, 2)
                            self.active_bet = {
                                "issue": cur_issue,
                                "choice": decision,
                                "stake": stake,
                                "confidence": confidence,
                                "strategy": strategy,
                                "time": time.time(),
                                "method": "DEMO SIMULATION"
                            }
                            self.total_bets_placed += 1
                            exp_badge = f" [🎯 Potential: {expected_nums}]" if expected_nums else ""
                            self.last_action_desc = f"🎯 <b>Prediction:</b> <b>{decision}</b>{exp_badge} (₹{stake:.2f}) | <i>{strategy}</i> [{confidence:.0f}%]"
                            self._update_status(cur_issue)
                        else:
                            bet_res = self.api.place_bet(cur_issue, decision, amount=stake, type_id=game_type_id)
                            if bet_res.get("ok"):
                                self.active_bet = {
                                    "issue": cur_issue,
                                    "choice": decision,
                                    "stake": stake,
                                    "confidence": confidence,
                                    "strategy": strategy,
                                    "time": time.time(),
                                    "method": bet_res.get("method", "API")
                                }
                                self.total_bets_placed += 1
                                exp_badge = f" [🎯 Potential: {expected_nums}]" if expected_nums else ""
                                self.last_action_desc = f"🎯 <b>Live Bet:</b> <b>{decision}</b>{exp_badge} (₹{stake:.2f}) | <i>{strategy}</i> [{confidence:.0f}%]"
                                self._update_status(cur_issue)
                            else:
                                self.last_action_desc = f"⚠️ <b>Bet Error:</b> {bet_res.get('msg')}"
                                self._update_status(cur_issue)
                    else:
                        self.skips += 1
                        self.last_action_desc = f"⏭️ <b>Auto Skip:</b> <i>{reason}</i> (No Risk)"
                        self._update_status(cur_issue)

                time.sleep(2.0)

            except Exception as e:
                print(f"[AUTOBET LOOP ERROR] {e}", flush=True)
                time.sleep(3.0)

        print("[+] WinGo Auto-Bet Loop Ended.", flush=True)

    def _resolve_previous_bet(self, issue_number: str, history: list):
        if not self.active_bet or self.active_bet.get("issue") != issue_number:
            return

        for it in history[-5:]:
            hist_iss = str(it.get("issueNumber") or it.get("period", ""))
            if hist_iss == str(issue_number):
                win_num = int(it.get("number", it.get("num", -1)))
                win_size = "BIG" if win_num >= 5 else "SMALL"
                bet_choice = self.active_bet["choice"]
                stake = self.active_bet["stake"]

                is_win = (win_size == bet_choice)
                if is_win:
                    self.wins += 1
                    self.current_loss_streak = 0
                    pnl = round(stake * 0.96, 2)
                    if self.is_demo:
                        self.current_balance = round(self.current_balance + (stake * 1.96), 2)
                    result_badge = "✅ <b>WIN</b>"
                else:
                    self.losses += 1
                    self.current_loss_streak += 1
                    pnl = -stake
                    result_badge = "❌ <b>LOSS</b>"

                if not self.is_demo:
                    self.current_balance = self.api.fetch_balance()

                record = {
                    "issue": issue_number,
                    "choice": bet_choice,
                    "result_size": win_size,
                    "result_num": win_num,
                    "is_win": is_win,
                    "stake": stake,
                    "pnl": pnl,
                    "balance": self.current_balance
                }
                self.history_records.append(record)

                # Update the last settled description for the pinned dashboard
                self.last_settled_desc = (
                    f"{result_badge} <code>{issue_number}</code>: "
                    f"Bet <b>{bet_choice}</b> | Drawn <b>{win_size} ({win_num})</b> | PnL <b>{'+' if pnl>=0 else ''}₹{pnl:.2f}</b>"
                )
                break
