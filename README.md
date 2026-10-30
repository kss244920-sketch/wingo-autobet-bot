# WinGo 3-Minute Deep-Reasoning Auto-Betting AI Bot

Autonomous AI prediction and micro-compounding betting bot for WinGo 3 Minutes.

## Key Features
- **WinGo 3 Minutes (180s Cycle)**: Generous 2-3 minute window allowing the AI to run deep statistical models without time pressure.
- **Deep AI Thinking Engine**:
  - 32 Statistical Quant algorithms (Markov, Fourier DFT, Beta-Binomial Bayesian, Weibull hazard, Roadmap pattern).
  - Groq Master AI Brain (`qwen/qwen3.8-27b`) with temperature 0.05.
- **Automatic Skips Preferred**: Strictly filters out volatile chaos (Δ > 5.2), 50/50 chop, and low-conviction signals (<82%).
- **Target-Driven Money Management (`/setamount <target>`)**:
  - Bot fetches current balance.
  - Places calculated safe micro-stakes (1.0% - 2.0% of balance, min ₹1).
  - **Auto-Stop on Target Achieved**: Automatically terminates all betting as soon as target balance is reached to lock in profits.
  - **Stop-Loss Floor (`/setstoploss <floor>`)**: Prevents drawdown past minimum floor.
- **Dual Execution Engine**:
  - Direct HTTP API (`/api/webapi/GameBetting`).
  - Seamless headless Selenium fallback if maintenance code 405 is reported.

## Telegram Bot Commands
- `/start` - Interactive dashboard with live balance, target progress, and quick buttons.
- `/login <phone> <password> [site_url]` - Login to account and fetch balance.
- `/setamount <target_balance>` - Set goal balance to achieve (e.g. `/setamount 500`).
- `/setstoploss <amount>` - Set minimum balance floor.
- `/start_betting` - Start autonomous 3-minute trading engine.
- `/stop_betting` - Safely stop/pause betting.
- `/status` - Live round, AI reasoning summary, and target progress bar.
- `/balance` - Check live wallet balance.
- `/history` - Recent rounds & PnL.

## Setup & Running
```bash
cd /home/piyush/wingo-autobet-bot
pip install -r requirements.txt
python3 bot.py
```
