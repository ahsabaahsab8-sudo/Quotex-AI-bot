# PROMPT: Build "Quotex AI Bot Service" (Customer-Support AI Assistant Bot)

> INSTRUCTIONS TO THE USER: Copy EVERYTHING below (from `===START PROMPT===` to `===END PROMPT===`) and paste it into your AI coding agent. Before you paste it, replace every `[FILL IN: ...]` placeholder with your real business details (pricing, free-signal count, channel links, support contact). Everything else is complete.

===START PROMPT===

You are an expert Python developer and Telegram bot engineer. Build a complete, production-ready Telegram bot called **"Quotex AI Bot Service"**.

## 1. PROJECT OVERVIEW

This is a NEW standalone project (separate folder, separate repo). Do NOT modify the existing Quotex signal bot. This new bot is a **customer-support / sales-assistant AI bot** for the existing "Quotex AI Bot" product. It answers users' questions about the Quotex AI Bot: how it works, what it does, how it connects to Quotex, what AI models it uses, its pricing, and its free-signal channel. It is a *knowledge assistant*, NOT a trading bot. It must never place trades or connect to Quotex.

## 2. BOT TOKEN

Use this Telegram bot token (via .env, NOT hardcoded):

```
8480481436:AAGPV1fAeVUqiRV61ua_-_D6RIZp_J6kCr0
```

## 3. TECH STACK & REQUIREMENTS

- Python 3.10+ (works on Windows and Linux VPS)
- `python-telegram-bot` (v20+ or v21+, the modern async API with `Application`)
- `python-dotenv` for .env loading
- AI/LLM integration via an OpenAI-compatible REST API (use the `openai` Python SDK or plain `requests`/`httpx`). Support the provider and key via `.env` so the user can swap providers.
- Keep dependencies minimal. Use asyncio throughout. No other frameworks needed.
- Structure the project cleanly:
  - `main.py` (entry point / bot launcher)
  - `bot.py` (Telegram handlers)
  - `knowledge_base.py` (all the Q&A content — this is the source of truth the AI answers from)
  - `ai.py` (LLM client with prompt building, JSON parsing, retries, and a keyword-fallback answerer)
  - `config.py` (reads .env)
  - `.env` / `.env.example`
  - `requirements.txt`
  - `README.md` with run instructions

## 4. REQUIRED BEHAVIOUR

### 4.1 Commands & flow
- `/start` → send a friendly welcome + short description of the bot, plus an inline keyboard: "💬 Ask about the Bot", "📋 Quick FAQ", "💰 Pricing", "📡 Free Signals", "🤖 AI Models", "📞 Contact Support". Each button opens the relevant info or an "ask freely" prompt.
- Any free-text message → treated as a question. The bot sends it (plus the system prompt + relevant knowledge base context) to the LLM and replies with the answer.
- Support inline keyboards with back navigation. All replies in clean, readable Telegram Markdown. Add a "typing…" indicator (ChatAction) before long answers.
- Handle unknown commands gracefully. Never crash on a bad message.
- Add a rate-limit / spam guard: a simple per-user cooldown (e.g. max 1 message per 2 seconds, and cap conversation length so the LLM prompt doesn't blow up).

### 4.2 AI integration
- Build the LLM prompt with: (a) a strong system persona, (b) the FULL knowledge base text below, (c) the user's question.
- Model: use an OpenAI-compatible endpoint configured in `.env` (e.g. `AI_API_KEY`, `AI_BASE_URL`, `AI_MODEL`). Use a good default like `deepseek-chat`, `gpt-4o-mini`, or `gemini-2.0-flash` — read from .env so it's swappable.
- Request JSON mode / low temperature (~0.3) so answers are factual and consistent.
- Implement: timeout (60s), 2 retries, and graceful fallback. If the LLM call fails, **always** fall back to a keyword-matching answerer built from the FAQ list below so the bot never goes silent.
- Keep context: remember last ~6 messages per user (simple in-memory dict) so follow-up questions work. Clear context on /start.

### 4.3 Config (.env)
```
TELEGRAM_BOT_TOKEN=8480481436:AAGPV1fAeVUqiRV61ua_-_D6RIZp_J6kCr0
AI_API_KEY=[FILL IN: your LLM provider API key]
AI_BASE_URL=[FILL IN: e.g. https://api.openai.com/v1 or your provider]
AI_MODEL=[FILL IN: e.g. deepseek-chat]
```

### 4.4 Deployment
- Provide a `systemd` service file example (for a Linux VPS) and a `start_bot.py`-style launcher that fixes Windows asyncio event-loop issues (call `asyncio.get_event_loop()` in a try/except before building the Application).
- Log to stdout with `logging`.

## 5. KNOWLEDGE BASE — THE QUOTEX AI BOT (feed ALL of this to the AI)

This is the complete, accurate description of the product the assistant must know. The assistant must answer ONLY based on this and never invent numbers the owner didn't set.

### 5.1 What it is
"Quotex AI Bot" is a Telegram-based AI trading signal bot for the **Quotex** binary-options trading platform. A user opens the bot, picks a market and an asset, and the bot analyzes the market with technical indicators AND three AI models in parallel, then sends a high-confidence **1-minute BUY (UP) / SELL (DOWN)** signal with a confidence percentage and a martingale (money-management) recommendation. After the 1-minute candle closes, the bot also reports whether the trade was a WIN or LOSS.

### 5.2 How it works, step by step (the user flow)
1. User opens the Telegram bot and presses **🔥 GET SIGNAL**.
2. Bot shows 3 market categories:
   - 💱 **OTC Currencies** (synthetic pairs, e.g. EURUSD_otc)
   - 📉 **Real Market Currencies** (e.g. EUR/USD)
   - 🪙 **Crypto & Commodities** (e.g. XAUUSD gold, BTCUSD, ETHUSD, XAGUSD, etc.)
3. User picks a specific pair. The bot shows a 5-step progress: *Connect to Quotex → Fetch candles & compute indicators → Math score → 3-stage AI pipeline → Send signal*.
4. The bot connects to Quotex with the owner's account (SSID session token) and downloads **18,000 historical 1-minute candles**.
5. It computes **20+ technical indicators** (see 5.4) on **1-minute, 5-minute and 15-minute** timeframes.
6. It produces a **math score (0–10)**. If the chosen pair scores below **7.0/10**, the bot **auto-scans the whole category** and switches to the best-scoring pair automatically (and tells the user it switched).
7. It runs the **3-AI-model voting pipeline** (see 5.5). Final direction = majority vote. A **risk judge** can downgrade confidence.
8. It sends the signal card: pair, signal direction (📈 BUY/UP or 📉 SELL/DOWN), confidence % (50–95), trade time in **Pakistan time (UTC+5)**, martingale recommendation (M0/M1/M2), and the current candle countdown.
9. After the trade window ends, the bot fetches the closed candle and posts **WIN** or **LOSS**.
10. Signals are **1-minute expiry trades** — the user waits for the current candle to finish, then places the trade at the exact trade time shown.

### 5.3 How it connects to Quotex (the technical part)
- It uses the **pyquotex** library over a **WebSocket** to Quotex's platform (host `market-quotex.pro`, websocket `wss://ws2.qxbroker.com/socket.io/`).
- Authentication uses an **SSID session token** extracted from the owner's Quotex account via automated browser login. Login methods, in order of preference: **Camoufox** (stealth Firefox, works on Windows + Linux, bypasses Cloudflare) → **Kameleo** (Windows only) → **undetected-chromedriver**. The OTP login code is **auto-read from Gmail via IMAP** when Quotex sends it.
- The SSID token is **auto-renewed** before expiry. A **watchdog refreshes it every 20 minutes** so it never expires mid-signal. If a connection hiccups, it retries with the same token before doing a full re-login.
- All traffic goes through a **SOCKS5 proxy** (`QUOTEX_PROXY` in .env) because Quotex geo-blocks certain regions; the httpx + websocket transports are runtime-patched to go through the proxy.
- The Quotex account must be in **REAL mode** (live trading account).

### 5.4 The technical indicators used (tell users it's "20+ indicators")
Trend: EMA 9/20/50/200 alignment (short + long term), ADX (trend strength), MACD, support/resistance break & retest.
Momentum: RSI (with directional change), Stochastic %K/%D, CCI, Williams %R, Awesome Oscillator, Money Flow Index (MFI).
Volatility: ATR (vs 20-period average), Bollinger Bands (squeeze), volatility expansion detection.
Structure/price action: Fair Value Gaps (FVG), liquidity sweep / stop-hunt traps, SMT divergence, candlestick patterns (Doji, Hammer, Shooting Star, Engulfing), wick (pin bar) analysis, pivot points (Pivot/R1/S1), Ichimoku Cloud, nearest round-number magnets.
Other: OTC candle color probability (historical next-candle green/red %, based on last 10 candles), 50-period high/low support & resistance, volume trend, session filter (London/NY overlap = high liquidity).

### 5.5 The AI models used in the bot
The bot runs a **3-stage AI pipeline** where three independent AI models analyze the same indicator data and **vote BUY or SELL**:
1. **GLM 5.2** (via NVIDIA's API) — primary analyst.
2. **DeepSeek V4 Flash** (via the OpenCode Zen gateway).
3. **Gemini 3.6 Flash** (Google Generative Language API).
The final signal is the **majority vote (2 of 3)**. Average confidence is clamped to 50–95%. A martingale recommendation is given: **M0** (no martingale) at lower confidence, **M1** (1-step martingale) at ≥75% confidence. The models are forced to output strict JSON and the prompt requires them to weigh 20 factors in 3 tiers (Tier 1 strong factors 70% weight, Tier 2 confirmations 20%, Tier 3 extra filters 10%). Even in unclear markets the models must pick BUY or SELL (never SKIP) with a confidence score. In practice the math-score gate (≥7.0/10) filters weak setups before the AI even runs.

### 5.6 Pricing / plans
[FILL IN: your real pricing. Example below — replace with your actual plans and prices.]

### 5.7 Free signals public channel
[FILL IN: your real numbers. Example below — replace.]

---

**Example placeholder content (REPLACE the two blocks above with your real info before pasting this prompt):**

**5.6 Pricing / plans (example)**
- **FREE Trial**: 3 free signals per day, no payment required.
- **BASIC**: [FILL IN price, e.g. $19/month] — [FILL IN number, e.g. 10] signals/day.
- **PREMIUM**: [FILL IN price, e.g. $49/month] — [FILL IN number, e.g. 25] signals/day.
- **VIP**: [FILL IN price, e.g. $99/month] — unlimited signals + priority support.
- Payment methods: [FILL IN, e.g. USDT, bank transfer]. Subscriptions are [FILL IN: monthly/one-time].

**5.7 Free signals public channel (example)**
- The bot posts [FILL IN number, e.g. 5] free signals per day in the public channel.
- Channel link: [FILL IN: https://t.me/yourchannel]
- More signals and all VIP features are available via the paid plans above.

**Support/contact**
- [FILL IN: e.g. admin Telegram @yourusername, or an email]

---

### 5.8 Ready-to-use FAQ answers the assistant MUST be able to answer from memory (add them to the knowledge base verbatim)

1. **What is this bot?**
   → "Quotex AI Bot" is an AI-powered signal bot for Quotex. It analyzes markets using 20+ technical indicators and 3 AI models, then sends 1-minute BUY/SELL signals with confidence ratings.

2. **How does the bot work?**
   → You press GET SIGNAL, pick a market category (OTC, Real, or Crypto & Commodities) and a pair. The bot connects to Quotex, downloads the last 18,000 candles, computes 20+ indicators on 1m/5m/15m timeframes, gives the pair a 0–10 math score (auto-switching to the best pair in the category if yours scores below 7), then 3 AI models vote on the direction. It sends a signal with trade time (PKT, UTC+5) and a martingale suggestion, then reports WIN/LOSS after the candle closes.

3. **Which pairs/categories are available?**
   → Three categories: OTC Currencies (e.g. EURUSD_otc), Real Market Currencies (e.g. EUR/USD), and Crypto & Commodities (XAUUSD, BTCUSD, ETHUSD, XAGUSD, and more). Pairs and payouts are fetched live from Quotex each time.

4. **How is the bot connected to Quotex?**
   → Through a private, automated Quotex account session (SSID token) over a secure WebSocket, routed through a proxy. The login is automated (Camoufox/Kameleo/undetected browser with auto OTP reading from email) and the session token auto-renews every 20 minutes so the connection never drops.

5. **What AI models does the bot use?**
   → Three models vote on every signal: GLM 5.2, DeepSeek V4 Flash, and Gemini 3.6 Flash. The majority vote (2 out of 3) becomes the signal, with confidence capped between 50% and 95%.

6. **How many free signals are in the public channel?**
   → [FILL IN answer based on your 5.7 settings.]

7. **What is the price of the bot?**
   → [FILL IN answer based on your 5.6 settings.]

8. **What does M0/M1/M2 martingale mean?**
   → M0 = no martingale, trade your normal amount. M1 = 1-step martingale (double once after a loss to recover). M2 = 2-step martingale (aggressive, doubles twice). The bot only recommends it based on confidence and always advises risk management.

9. **What is the signal timeframe?**
   → Every signal is a **1-minute** trade. You place the trade right after the current candle closes, at the trade time shown in the signal.

10. **Is it safe / guaranteed profit?**
    → No bot can guarantee profit. Trading binary options carries high risk. The bot uses math scoring + multi-model voting to raise the probability of a good setup, but you should always use proper risk management, small trade amounts, and never trade money you can't afford to lose.

11. **Do I need a Quotex account?**
    → Yes. The bot sends signals; you place the trades in your own Quotex account. The bot does not trade for you and does not touch your money.

12. **Why did the bot switch my pair?**
    → Your chosen pair scored below 7/10 (weak setup), so the bot auto-scanned the whole category and picked the strongest available pair instead. This is a feature to improve signal quality.

13. **Why did I get WIN/LOSS after my signal?**
    → After the 1-minute candle closes, the bot checks the actual candle result against the prediction and reports whether the signal won or lost, so you can track accuracy.

14. **Which timezone is the trade time in?**
    → Pakistan Standard Time (PKT, UTC+5).

15. **Where do I get support / how do I subscribe?**
    → [FILL IN: contact details from 5.6/5.7.]

## 6. CONSTRAINTS & QUALITY BAR

- The assistant must ALWAYS answer factually from the knowledge base above. If it doesn't know, it must say it doesn't know and point the user to the FAQ/support, never hallucinate.
- Do not promise profit. Never give financial advice beyond the product description. If a user asks "should I trade?", respond responsibly: signal bots don't guarantee profit; use risk management.
- Keep answers in the same language the user asks in.
- The bot must not require any payment gateway, database, or external service beyond the Telegram API and the LLM API. Keep it simple to host on one VPS.
- Code must be clean, typed, commented, and follow PEP8. No secrets in code — everything from .env.

## 7. DELIVERABLES CHECKLIST

1. Working Telegram bot that responds to /start, the inline menu, and free-text questions.
2. Knowledge base module containing ALL content from section 5 (with the FILL IN values provided).
3. AI module: OpenAI-compatible client + prompt builder + strict-JSON handling + retries + keyword fallback.
4. Per-user context memory (last ~6 messages) and rate-limit guard.
5. .env.example, requirements.txt, README.md, and a systemd example.
6. Verify: run `python main.py` and test /start, a menu button, and 3 sample questions (e.g. "How does the bot work?", "What AI models do you use?", "What is the price?") — show the results.

Build it now, fully working, in a new folder named `quotex-ai-service`.

===END PROMPT===
