# 📈 Quotex AI Bot — Autonomous Multi-Model Signal & Analysis System 🤖📊

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://python.org)
[![Telegram](https://img.shields.io/badge/Telegram-Bot%20API-2CA5E0?logo=telegram&logoColor=white)](https://telegram.org)
[![Playwright / Camoufox](https://img.shields.io/badge/Browser-Camoufox%20Stealth-orange)](https://github.com/daijro/camoufox)
[![AI Ensemble](https://img.shields.io/badge/AI%20Voting-GLM%205.2%20%7C%20DeepSeek%20%7C%20Gemini-green)](https://github.com)
[![License](https://img.shields.io/badge/License-Proprietary-red.svg)](LICENSE)

> ⚡ **An autonomous algorithmic trading signal bot for Quotex binary options.**  
> Built with 20+ technical indicators across multi-timeframe candles, automated Camoufox stealth session renewal with Gmail IMAP OTP extraction, a 0–10 mathematical quality filter, and a 3-stage consensus AI voting engine (GLM 5.2, DeepSeek V4 Flash, and Google Gemini).

---

## 🌟 Core System Features

* 💱 **Multi-Market Live Asset Coverage**:
  * **OTC Synthetic Currencies** (e.g. `EURUSD_otc`, `GBPUSD_otc`, `USDJPY_otc`)
  * **Real Market FX Pairs** (e.g. `EUR/USD`, `GBP/JPY`)
  * **Commodities & Cryptocurrencies** (`XAUUSD Gold`, `BTCUSD`, `ETHUSD`, `XAGUSD Silver`)
* 📊 **Deep Historical Market Analysis**:
  * Downloads **18,000 historical 1-minute candles** directly via Quotex WebSocket feeds.
  * Calculates **20+ mathematical and technical indicators** across 1m, 5m, and 15m frames.
* 🎯 **Mathematical Quality Filter (Math Score $\ge$ 7.0/10)**:
  * Pairs scoring below 7.0/10 are automatically rejected; the bot auto-scans the entire asset category and automatically selects the highest-scoring opportunity.
* 🤖 **3-AI Ensemble Consensus Pipeline**:
  * **Model 1**: GLM 5.2 (NVIDIA API Gateway)
  * **Model 2**: DeepSeek V4 Flash (OpenCode Zen Gateway)
  * **Model 3**: Google Gemini 3.6 Flash
  * Direction requires a strict majority vote (2 out of 3) with confidence rating (50%–95%) and Martingale guidance (`M0` / `M1` / `M2`).
* 🔄 **Automated Stealth Session & OTP Renewal**:
  * Uses **Camoufox** (anti-detect headless stealth browser) to solve Cloudflare turns and log in.
  * Auto-retrieves 2FA email verification codes directly from Gmail via IMAP.
  * 20-minute session watchdog ensures token never drops or expires mid-trade.
* 🏆 **Automated Trade Resolution**:
  * Waits for the 1-minute candle to close and automatically broadcasts **WIN** or **LOSS** confirmation.

---

## 🏗️ Signal Generation Architecture

```
┌─────────────────────┐      ┌─────────────────────────┐      ┌─────────────────────────┐
│ User Asset Pick     │ ───> │ Quotex WebSocket Feed   │ ───> │ 18k Candle Analysis     │
│ (OTC, FX, Crypto)   │      │ (Camoufox SSID Session) │      │ (20+ Tech Indicators)   │
└─────────────────────┘      └─────────────────────────┘      └───────────┬─────────────┘
                                                                          │
┌─────────────────────┐      ┌─────────────────────────┐      ┌───────────▼─────────────┐
│ 1-Min Signal Output │ <─── │ 3-Model AI Voting:      │ <─── │ Math Quality Gate       │
│ & Win/Loss Monitor  │      │ GLM + DeepSeek + Gemini │      │ (Score >= 7.0 Filter)   │
└─────────────────────┘      └─────────────────────────┘      └─────────────────────────┘
```

---

## 🛠️ Technical Indicators Computed

1. **Trend & Momentum**: EMA 9, 20, 50, 200 ribbon; ADX trend strength; MACD histogram; RSI with momentum slope; Stochastic %K/%D; CCI; Williams %R; Money Flow Index (MFI).
2. **Volatility & Squeeze**: Average True Range (ATR); Bollinger Bands squeeze & expansion detection.
3. **Price Action & Smart Money Concepts (SMC)**: Fair Value Gaps (FVG); Liquidity sweeps & stop-hunts; Support & Resistance pivot levels; Candlestick pattern recognition (Hammer, Doji, Engulfing, Pin bars).
4. **OTC Synthetic Specifics**: Historical next-candle color probability distribution based on trailing 10-candle series.

---

## 🔑 Environment Variables Setup (`.env`)

Create `.env` based on `.env.example`:

```bash
cp .env.example .env
```

| Variable | Required | Description |
| :--- | :---: | :--- |
| `QUOTEX_EMAIL` | **Yes** | Your Quotex account email address |
| `QUOTEX_PASSWORD` | **Yes** | Your Quotex account password |
| `TELEGRAM_BOT_TOKEN` | **Yes** | Telegram bot token from [@BotFather](https://t.me/BotFather) |
| `GEMINI_API_KEY` | **Yes** | Google AI Studio Gemini API key |
| `DEEPSEEK_API_KEY` | **Yes** | DeepSeek / OpenCode Zen API key |
| `NVIDIA_NEMOTRON_API_KEY`| **Yes** | NVIDIA API gateway key for GLM / Nemotron models |
| `IMAP_EMAIL` | **Yes** | Gmail address where Quotex sends login OTP codes |
| `IMAP_PASSWORD` | **Yes** | Gmail 16-character App Password for IMAP access |
| `CAMOUFOX_USE_PROXY` | No | Set `true` if routing browser automation through proxy |
| `TELEGRAM_PROXY` | No | Optional SOCKS5 proxy URL for Telegram connectivity |

---

## 🚀 Installation & Local Run

### 1. Prerequisites
- **Python 3.10+** (Python 3.11/3.12 recommended)
- **Node.js** & modern browser dependencies for Camoufox

### 2. Setup Virtual Environment
```bash
# Clone the repository
git clone https://github.com/ahsabaahsab8-sudo/Quotex-AI-bot.git
cd Quotex-AI-bot

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Verify Quotex Connectivity & Adapter
```bash
# Test adapter connection and session token handshake
python test_adapter.py
```

### 4. Start the Bot
```bash
# Run the interactive signal bot
python start_bot.py
```

---

## ☁️ 24/7 Linux VPS Deployment

### 1. Automated 24/7 Shell Loop (`run_24_7.sh`)
```bash
chmod +x run_24_7.sh
./run_24_7.sh
```

### 2. Production `systemd` Service Setup

1. Create service configuration:
   ```bash
   sudo nano /etc/systemd/system/quotex-bot.service
   ```

2. Insert unit definition:
   ```ini
   [Unit]
   Description=Quotex AI Signal Bot Daemon
   After=network.target

   [Service]
   Type=simple
   User=root
   WorkingDirectory=/opt/Quotex-AI-bot
   EnvironmentFile=/opt/Quotex-AI-bot/.env
   ExecStart=/opt/Quotex-AI-bot/.venv/bin/python start_bot.py
   Restart=always
   RestartSec=10

   [Install]
   WantedBy=multi-user.target
   ```

3. Enable and start:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now quotex-bot
   sudo systemctl status quotex-bot
   ```

---

## 📂 Project Architecture

```
Quotex-AI-bot/
├── .env.example              # Sanitized configuration template
├── start_bot.py              # Main bot launch controller with watchdog
├── quotex_adapter.py         # PyQuotex / A11ksa WebSocket client wrapper
├── chart_capture.py          # Real-time candlestick extraction & plotting
├── chart_render.py           # Candlestick chart rendering engine
├── gmail_otp.py              # Automated Gmail IMAP reader for 2FA OTP codes
├── playwright_login.py       # Camoufox stealth browser automation
├── renew_ssid.py             # Automatic 20-minute session renewal loop
├── run_24_7.sh               # Infinite recovery shell launcher
├── session_manager.py        # Token cache and disk session persistence
├── requirements.txt          # Python dependencies
└── webapp/                   # Optional web dashboard
```

---

## ⚠️ Risk & Disclaimer Notice

* **High Risk Warning**: Financial trading and binary options involve substantial risk of loss and are not suitable for every investor.
* **No Financial Advice**: This software is designed for research, algorithmic education, and automated indicator computation. Never trade funds you cannot afford to lose. Always employ disciplined risk management and paper trade first.

---

## 📄 License

Proprietary Software. Developed by Ahsan Ali / Deep Minded Services Limited. All rights reserved.
