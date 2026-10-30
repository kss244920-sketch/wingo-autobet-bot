import time
import json
import uuid
import hashlib
import requests
import re
from typing import Dict, Any, Optional

UA_MOB = (
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Mobile Safari/537.36"
)

def mz() -> str:
    return uuid.uuid4().hex

def signed_body(body: Dict[str, Any]) -> Dict[str, Any]:
    t = dict(body)
    t.pop("signature", None)
    t.pop("timestamp", None)
    t["language"] = 0
    t["random"] = mz()

    gue = {"signature", "track", "xosoBettingData"}
    n = {}
    for k in sorted(t.keys()):
        v = t[k]
        if v is not None and v != "" and k not in gue:
            n[k] = 0 if v == 0 else v

    json_str = json.dumps(n, separators=(",", ":"))
    sig = hashlib.md5(json_str.encode()).hexdigest().upper()
    t["signature"] = sig
    t["timestamp"] = int(time.time())
    return t


class WinGoAPIClient:
    def __init__(self, site: str = "https://www.dmfirst17.com", api: str = "https://api.dmfirst9api.com"):
        self.site = site.rstrip("/")
        self.api = api.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": UA_MOB,
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json;charset=UTF-8",
            "Ar-Origin": self.site,
            "Origin": self.site,
            "Referer": f"{self.site}/",
            "Accept-Language": "en-IN,en;q=0.9",
        })
        self.token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.lottery_login_url: Optional[str] = None
        self.user_id: Optional[str] = None
        self.phone: Optional[str] = None
        self.password: Optional[str] = None
        self.nick_name: Optional[str] = None
        self.balance: float = 0.0

    def login(self, phone: str, password: str, site: Optional[str] = None, api: Optional[str] = None) -> Dict[str, Any]:
        if site:
            self.site = site.rstrip("/")
        if api:
            self.api = api.rstrip("/")

        clean_phone = re.sub(r"\D", "", phone)[-10:]
        self.phone = clean_phone
        self.password = password

        payload = {
            "username": f"91{clean_phone}",
            "pwd": password,
            "loginType": "mobile",
            "phonetype": 1,
        }
        body = signed_body(payload)
        res = self.session.post(f"{self.api}/api/webapi/Login", json=body, timeout=12)
        j = res.json()

        if j.get("code") == 0 and j.get("data"):
            d = j["data"]
            self.token = d.get("token")
            self.refresh_token = d.get("refreshToken")
            self.lottery_login_url = d.get("lotteryLoginUrl")
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})

            # Fetch User Profile & Balance
            self.fetch_user_profile()
            self.fetch_balance()

            return {
                "ok": True,
                "msg": "Login Successful",
                "userId": self.user_id,
                "nickName": self.nick_name,
                "balance": self.balance,
                "token": self.token
            }
        else:
            return {
                "ok": False,
                "msg": j.get("msg", "Login Failed"),
                "code": j.get("code", -1)
            }

    def fetch_user_profile(self) -> Dict[str, Any]:
        if not self.token:
            return {}
        try:
            body = signed_body({})
            r = self.session.post(f"{self.api}/api/webapi/GetUserInfo", json=body, timeout=10)
            j = r.json()
            if j.get("code") == 0 and j.get("data"):
                d = j["data"]
                self.user_id = str(d.get("userId", ""))
                self.nick_name = str(d.get("nickName", ""))
                return d
        except Exception as e:
            print(f"[API ERROR] GetUserInfo: {e}")
        return {}

    def fetch_balance(self) -> float:
        if not self.token:
            return 0.0
        try:
            body = signed_body({})
            r = self.session.post(f"{self.api}/api/webapi/GetUserAmount", json=body, timeout=8)
            j = r.json()
            if j.get("code") == 0 and j.get("data"):
                self.balance = float(j["data"].get("amount", 0.0))
                return self.balance
        except Exception as e:
            print(f"[API ERROR] GetUserAmount: {e}")
        return self.balance

    def get_current_issue(self, type_id: int = 2) -> Dict[str, Any]:
        """Fetch current issue and timing for game type (2 = WinGo 3M)."""
        try:
            body = signed_body({"typeId": type_id})
            r = self.session.post(f"{self.api}/api/webapi/GetGameIssue", json=body, timeout=8)
            j = r.json()
            if j.get("code") == 0 and j.get("data"):
                return j["data"]
        except Exception as e:
            print(f"[API ERROR] GetGameIssue: {e}")
        return {}

    def get_history(self, history_url: str = "https://draw.ar-lottery01.com/WinGo/WinGo_3M/GetHistoryIssuePage.json") -> list:
        """Fetch latest draw history from draw engine and maintain persistent rolling cache."""
        import os
        cache_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "history_cache.json")
        cached = []
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r") as f:
                    cached = json.load(f)
            except Exception:
                pass

        try:
            r = requests.get(history_url, timeout=8)
            if r.status_code == 200:
                j = r.json()
                data = j.get("data", {})
                new_items = data.get("list", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                
                # Merge new items into cached history by issueNumber or period
                seen_issues = {str(it.get("issueNumber") or it.get("period")) for it in cached if (it.get("issueNumber") or it.get("period"))}
                for item in reversed(new_items):
                    iss = str(item.get("issueNumber") or item.get("period", ""))
                    if iss and iss not in seen_issues:
                        item["issueNumber"] = iss
                        item["period"] = iss
                        cached.append(item)
                        seen_issues.add(iss)

                # Keep rolling 300 rounds
                if len(cached) > 300:
                    cached = cached[-300:]

                with open(cache_path, "w") as f:
                    json.dump(cached, f, indent=2)
        except Exception as e:
            print(f"[API ERROR] get_history: {e}")

        return cached

    def place_bet_api(self, issue_number: str, choice: str, amount: int = 1, type_id: int = 2) -> Dict[str, Any]:
        """
        Place bet directly through AR-SAAS API.
        choice: BIG (selectType: 13, gameType: 2) | SMALL (selectType: 14, gameType: 2)
                RED (selectType: 10, gameType: 0) | GREEN (selectType: 11, gameType: 0)
        """
        choice_upper = choice.upper()
        if choice_upper == "BIG":
            select_type, game_type = 13, 2
        elif choice_upper == "SMALL":
            select_type, game_type = 14, 2
        elif choice_upper == "RED":
            select_type, game_type = 10, 0
        elif choice_upper == "GREEN":
            select_type, game_type = 11, 0
        else:
            return {"ok": False, "msg": f"Unsupported choice: {choice}"}

        payload = {
            "typeId": type_id,
            "issuenumber": str(issue_number),
            "amount": int(amount),
            "betCount": 1,
            "gameType": game_type,
            "selectType": select_type,
        }
        body = signed_body(payload)
        try:
            r = self.session.post(f"{self.api}/api/webapi/GameBetting", json=body, timeout=10)
            j = r.json()
            code = j.get("code")
            msg = j.get("msg", "")

            if code == 0:
                return {"ok": True, "code": code, "msg": msg, "method": "API"}
            else:
                return {"ok": False, "code": code, "msg": msg, "method": "API"}
        except Exception as e:
            return {"ok": False, "code": -1, "msg": str(e), "method": "API"}

    def place_bet_selenium_fallback(self, choice: str, amount: int = 1) -> Dict[str, Any]:
        """
        Fallback automation using Selenium headless browser in case API reports maintenance code 405.
        """
        if not self.phone or not self.password:
            return {"ok": False, "msg": "Missing credentials for Selenium fallback", "method": "SELENIUM"}

        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By

        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=412,915")
        chrome_options.add_argument(f"--user-agent={UA_MOB}")

        driver = None
        try:
            driver = webdriver.Chrome(options=chrome_options)
            driver.get(f"{self.site}/#/login")
            time.sleep(2.5)

            inputs = driver.find_elements(By.TAG_NAME, "input")
            if len(inputs) >= 3:
                inputs[1].send_keys(self.phone)
                inputs[2].send_keys(self.password)
                time.sleep(0.5)

            login_btns = [b for b in driver.find_elements(By.TAG_NAME, "button") if "Log in" in b.text]
            if login_btns:
                login_btns[0].click()
                time.sleep(3.5)

            # Navigate to WinGo 3M
            driver.get(f"{self.site}/#/home/AllLotteryGames/WinGo")
            time.sleep(3.5)

            # Switch tab to WinGo 3Min if needed
            tab_3m = driver.find_elements(By.XPATH, "//*[contains(text(), '3Min') or contains(text(), '3 minute')]")
            if tab_3m:
                tab_3m[0].click()
                time.sleep(1.0)

            # Click selection button
            choice_upper = choice.upper()
            target_cls = "Betting__C-foot-b" if choice_upper == "BIG" else "Betting__C-foot-s"
            if choice_upper == "GREEN":
                target_cls = "Betting__C-head-g"
            elif choice_upper == "RED":
                target_cls = "Betting__C-head-r"

            sel_btn = driver.find_element(By.CLASS_NAME, target_cls)
            sel_btn.click()
            time.sleep(1.0)

            # Adjust quantity if amount > 1
            if amount > 1:
                plus_btn = driver.find_elements(By.XPATH, "//div[contains(@class, 'Betting__Popup-btn') and text()='+']")
                if plus_btn:
                    for _ in range(min(amount - 1, 20)):
                        plus_btn[0].click()
                        time.sleep(0.08)

            # Click confirm bet
            confirm_btn = driver.find_element(By.CLASS_NAME, "Betting__Popup-foot-s")
            confirm_btn.click()
            time.sleep(1.5)

            toasts = driver.find_elements(By.CLASS_NAME, "van-toast")
            toast_text = " | ".join([t.text for t in toasts if t.text])

            return {"ok": True, "msg": f"Placed via Browser ({toast_text})", "method": "SELENIUM"}
        except Exception as e:
            return {"ok": False, "msg": f"Selenium fallback error: {e}", "method": "SELENIUM"}
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

    def place_bet(self, issue_number: str, choice: str, amount: int = 1, type_id: int = 2) -> Dict[str, Any]:
        """Primary API attempt with seamless Selenium fallback if maintenance code 405."""
        res = self.place_bet_api(issue_number, choice, amount, type_id)
        if not res["ok"] and res.get("code") == 1 and "maintained" in res.get("msg", "").lower():
            print("[+] API in maintenance, engaging Selenium fallback...")
            res_sel = self.place_bet_selenium_fallback(choice, amount)
            return res_sel
        return res
