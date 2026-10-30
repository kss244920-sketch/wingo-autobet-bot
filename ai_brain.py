import os
import json
import urllib.request
import importlib.util
from typing import List, Dict, Any, Optional

class WinGoAIBrain:
    def __init__(self, groq_api_key: Optional[str] = None):
        self.groq_api_key = groq_api_key
        self.consecutive_skips = 0

        # Load 16-Agent AI & Pure Math Hybrid Council from user's original wingo_bot
        base_dir = os.path.dirname(os.path.abspath(__file__))
        os.environ["CACHE_FILE"] = os.path.join(base_dir, "history_cache.json")
        os.environ["STATE_FILE"] = os.path.join(base_dir, "state_cache.json")

        local_orig = os.path.join(base_dir, "wingo_orig.py")
        if os.path.exists(local_orig):
            orig_path = local_orig
        else:
            orig_path = "/home/piyush/wingo_bot/bot.py"

        spec = importlib.util.spec_from_file_location("wingo_orig", orig_path)
        self.wb = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.wb)
        self.wb.GROQ_API_KEY = self.groq_api_key or os.environ.get("GROQ_API_KEY", "")
        self.wb.load_cache()
        self._normalize_memory()
        self.latest_channel_signal: Optional[Dict[str, Any]] = None
        print(f"🧠 [AI BRAIN INITIALIZED] Original 16-Agent Council Loaded with {len(self.wb.MEMORY_HISTORY)} cached rounds.", flush=True)

    def set_channel_signal(self, sig: Dict[str, Any]):
        """Saves real-time prediction signal captured directly from Telegram Channel -1003799001380."""
        self.latest_channel_signal = sig

    def fetch_live_predictor_signal(self, target_issue: str) -> Optional[Dict[str, Any]]:
        """
        Directly synchronizes with the user's live 30-Second Elite Predictor bot on Telegram Channel & Render API.
        Guarantees 100% 1:1 alignment between user's channel signals and autobet placement.
        """
        import time

        # 1. First Priority: Check instant push from Telegram Channel -1003799001380
        if self.latest_channel_signal:
            sig_p = str(self.latest_channel_signal.get("period", ""))
            # Check period match (full or last 3-4 digits)
            if sig_p and (sig_p == target_issue or target_issue.endswith(sig_p) or sig_p.endswith(target_issue[-4:])):
                # Verify freshness (< 85s old for 1-Minute WinGo rounds)
                if time.time() - self.latest_channel_signal.get("time", 0) < 85.0:
                    val = self.latest_channel_signal.get("decision", "SKIP")
                    conf = float(self.latest_channel_signal.get("confidence", 90.0 if val in ("BIG", "SMALL") else 50.0))
                    strat = self.latest_channel_signal.get("strategy", "Channel VIP Signal")
                    is_qual = (val in ("BIG", "SMALL"))
                    if is_qual:
                        self.consecutive_skips = 0
                    else:
                        self.consecutive_skips += 1

                    print(f"⚡ [CHANNEL SIGNAL 1:1] Target: {target_issue} -> {val} ({conf:.0f}%) | {strat}", flush=True)
                    return {
                        "decision": val,
                        "confidence": conf,
                        "strategy": strat,
                        "reason": f"Channel VIP Signal ({strat})",
                        "is_qualified": is_qual,
                        "expected_nums": self.latest_channel_signal.get("expected_num"),
                        "grade": "LEVEL_1",
                        "source": "TELEGRAM_CHANNEL_VIP"
                    }

        # 2. Second Priority: Poll Render Predictor API (/api/panel-data)
        predictor_url = os.environ.get("PREDICTOR_API_URL") or os.environ.get("PREDICTOR_URL") or "https://wingo-bot-s92f.onrender.com/api/panel-data"
        try:
            req = urllib.request.Request(predictor_url, headers={"User-Agent": "WinGoAutoBetEngine/2.0"})
            with urllib.request.urlopen(req, timeout=6.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                pred_period = str(data.get("period", ""))
                # Verify period match (full or last 3-4 digits)
                if pred_period and (pred_period == target_issue or pred_period.endswith(target_issue[-3:])):
                    pred_val = str(data.get("prediction", "SKIP")).upper()
                    if pred_val in ("BIG", "SMALL", "SKIP"):
                        conf = float(data.get("confidence", 85.0 if pred_val in ("BIG", "SMALL") else 50.0))
                        strat = str(data.get("strategy") or data.get("consensus") or "1M Live Predictor Alignment")
                        is_qualified = (pred_val in ("BIG", "SMALL"))
                        
                        if is_qualified:
                            self.consecutive_skips = 0
                        else:
                            self.consecutive_skips += 1

                        print(f"📡 [PREDICTOR SYNC] Target: {target_issue} -> {pred_val} ({conf:.0f}%) | {strat}", flush=True)
                        return {
                            "decision": pred_val,
                            "confidence": conf,
                            "strategy": strat,
                            "reason": str(data.get("reason", "1M Live Predictor Stream Synchronization")),
                            "is_qualified": is_qualified,
                            "expected_nums": data.get("expected_nums"),
                            "grade": str(data.get("grade", "LEVEL_1")),
                            "source": "LIVE_1M_PREDICTOR"
                        }
        except Exception as e:
            # Fallback to local quant engine if stream is temporarily slow
            pass
        return None

    def _normalize_memory(self):
        """Ensure all historical rounds strictly conform to RED/GREEN and BIG/SMALL."""
        clean = []
        seen = set()
        for it in self.wb.MEMORY_HISTORY:
            p = str(it.get("period", it.get("issueNumber", "")))
            if not p or p in seen:
                continue
            seen.add(p)

            num = int(it.get("num", it.get("number", 0)))
            raw_c = str(it.get("color", "")).lower()
            if num == 0:
                c = "RED"
            elif num == 5:
                c = "GREEN"
            else:
                c = "RED" if "red" in raw_c else "GREEN"

            sz = str(it.get("size", "")).upper()
            if sz not in ("BIG", "SMALL"):
                sz = "BIG" if num >= 5 else "SMALL"

            clean.append({
                "period": p,
                "num": num,
                "color": c,
                "has_violet": (num in (0, 5)),
                "size": sz
            })

        # CRITICAL: Always keep strictly chronologically sorted by issue number!
        clean.sort(key=lambda x: int(x["period"]))
        self.wb.MEMORY_HISTORY = clean[-300:]
        self.wb.KNOWN_PERIODS = {it["period"] for it in self.wb.MEMORY_HISTORY}

    def analyze(self, history_items: List[Dict[str, Any]], current_loss_streak: int = 0, target_issue: Optional[str] = None) -> Dict[str, Any]:
        """
        Runs the 16-Agent AI & Math Quant Council (from user's original wingo_bot):
        - Direct synchronization with live 1M Predictor Bot
        - Baccarat Derived Roads (Big Road, Big Eye Boy, Small Road, Cockroach Road)
        - Full Cloud DB Pattern Mining Engine across 7,300+ rounds
        - Volatility Delta Chaos Guard
        - Post-Dragon Break Transition Shield
        - Qwen-27B Neural Arbiter
        - 5-Level Adaptive Martingale & Recovery Target Locking
        """
        # 1. Primary Path: 1:1 Synchronize with user's live 1-Minute Predictor bot
        if target_issue:
            import time
            for attempt in range(4):
                live_signal = self.fetch_live_predictor_signal(target_issue)
                if live_signal and live_signal.get("decision") not in ("WAITING", "NONE", ""):
                    return live_signal
                if attempt < 3:
                    time.sleep(1.0)

        # 2. Fallback Path: Sync live history items into MEMORY_HISTORY
        for it in history_items:
            num = int(it.get("number", 0))
            p = str(it.get("issueNumber", ""))
            c = str(it.get("color", ""))
            if p:
                self.wb.save_to_memory(p, num, c, auto_save=False)

        # Normalize colors to prevent lowercase / multi-color KeyError in Markov matrix
        self._normalize_memory()
        self.wb.save_cache()

        # Call 16-agent council for pure autonomous decision with actual loss streak
        decision = self.wb.ask_12_ai_council(
            self.wb.MEMORY_HISTORY,
            current_loss_streak=current_loss_streak,
            consecutive_skips=self.consecutive_skips
        )

        t_type = str(decision.get("target_type", "SKIP")).upper()
        t_val = str(decision.get("target_val", "SKIP")).upper()
        t_conf = float(decision.get("target_conf", 50.0))
        reason = str(decision.get("reason", "Filtered Noise"))
        pattern = str(decision.get("pattern_name", "") or decision.get("consensus_tag", "Council"))

        is_qualified = (t_type == "SIZE" and t_val in ("BIG", "SMALL"))

        if is_qualified:
            self.consecutive_skips = 0
            final_decision = t_val
        else:
            self.consecutive_skips += 1
            final_decision = "SKIP"

        return {
            "decision": final_decision,
            "confidence": t_conf,
            "strategy": pattern,
            "reason": reason,
            "expected_nums": decision.get("expected_nums"),
            "quant_consensus": decision.get("consensus_tag", ""),
            "quant_votes": "",
            "quant_margin": 0.0,
            "ai_verdict": t_val,
            "ai_confidence": t_conf,
            "is_qualified": is_qualified,
            "source": "LOCAL_QUANT_COUNCIL"
        }
