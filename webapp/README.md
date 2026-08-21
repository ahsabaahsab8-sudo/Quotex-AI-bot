# Quotex AI Pro Dashboard

Premium trading-signals dashboard for your Quotex bot. One Python process runs
the FastAPI website + the same signal engine + one shared Quotex SSID.

## Run locally

```bash
# 1. Install deps (also needs your bot stack: openai, pandas, ta, pyquotex…)
pip install -r webapp/requirements.txt

# 2. Make sure you have a valid Quotex session (fresh SSID)
python renew_ssid.py

# 3. Start the dashboard
python -m uvicorn webapp.app:app --host 0.0.0.0 --port 8000

# 4. Open http://localhost:8000 and use Demo Login (or Google)
```

## .env options

| var | meaning |
|---|---|
| `GOOGLE_CLIENT_ID` | enables real Google login |
| `ALLOW_DEMO_LOGIN=1` | shows the demo login button (default on without Google) |
| `STRIPE_SECRET_KEY` | real Stripe checkout (otherwise mock instant checkout) |
| `DASHBOARD_JWT_SECRET` | session-cookie signing secret |
| `DASHBOARD_BASE_URL` | base URL for Stripe redirects |

## Menus

- **Home** — credits, win rate, usage, recent signals
- **Live Chart** — real-time Quotex candles over websocket
- **LLM Signals** — 3-LLM vote (Nemotron Ultra / Llama 3.1 8B / Laguna-S 2.1)
- **Vision Signals** — 3-vision vote with chart image (Gemini Flash / Muse Glimmer / Llama Vision)
- **My Signals** — full history + per-model reasoning
- **Credits & Billing** — ledger + balance
- **Pricing** — Free 120 / Starter $20=2000 / Pro $100=40000

## Credits logic

- 120 free credits on first signup
- 10 credits reserved per signal; charged only on a produced signal
- auto-refund on failure / low-volatility skip

## Deploy (VPS)

Same repo as the bot. `git pull`, then run both website + bot as one systemd
service pointing at the same folder / `session.json`.