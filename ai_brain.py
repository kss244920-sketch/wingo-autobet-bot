import os
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

        spec = importlib.util.spec_from_file_location("wingo_orig", "/home/piyush/wingo_bot/bot.py")
        self.wb = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.wb)
        self.wb.load_cache()
        self._normalize_memory()
        print(f"🧠 [AI BRAIN INITIALIZED] Original 16-Agent Council Loaded with {len(self.wb.MEMORY_HISTORY)} cached rounds.", flush=True)

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

    def analyze(self, history_items: List[Dict[str, Any]], current_loss_streak: int = 0) -> Dict[str, Any]:
        """
        Runs the 16-Agent AI & Math Quant Council (from user's original wingo_bot):
        - Baccarat Derived Roads (Big Road, Big Eye Boy, Small Road, Cockroach Road)
        - Full Cloud DB Pattern Mining Engine across 7,300+ rounds
        - Volatility Delta Chaos Guard
        - Post-Dragon Break Transition Shield
        - Qwen-27B Neural Arbiter
        - 5-Level Adaptive Martingale & Recovery Target Locking
        """
        # 1. Sync live history items into MEMORY_HISTORY
        for it in history_items:
            num = int(it.get("number", 0))
            p = str(it.get("issueNumber", ""))
            c = str(it.get("color", ""))
            if p:
                self.wb.save_to_memory(p, num, c, auto_save=False)

        # 2. Normalize colors to prevent lowercase / multi-color KeyError in Markov matrix
        self._normalize_memory()
        self.wb.save_cache()

        # 3. Always keep AI flexible and independent (autonomous trend-following, no blind Martingale trap)
        self.wb.CURRENT_CYCLE_TARGET = None
        self.wb.CURRENT_LOSS_STREAK = 0

        # 4. Call 16-agent council for pure autonomous decision
        decision = self.wb.ask_12_ai_council(
            self.wb.MEMORY_HISTORY,
            current_loss_streak=0,
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
            "quant_consensus": decision.get("consensus_tag", ""),
            "quant_votes": "",
            "quant_margin": 0.0,
            "ai_verdict": t_val,
            "ai_confidence": t_conf,
            "is_qualified": is_qualified
        }
