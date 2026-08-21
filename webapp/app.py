"""Quotex AI Dashboard — FastAPI app (single process, same folder as the bot).

Run locally:
    python -m uvicorn webapp.app:app --host 0.0.0.0 --port 8000

Everything (dashboard API + signal worker + optional bot) shares the same
session.json / SSID so there is only ONE Quotex identity.
"""
import asyncio
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect, Depends
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .database import init_db, make_session_factory, User, Job, Signal, CreditTransaction, utcnow
from . import auth as auth_mod
from . import credits as credits_mod
from . import billing
from .signal_runner import SignalWorker
from .live import LiveChartManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("dashboard")

STATIC_DIR = Path(__file__).parent / "static"
session_factory = make_session_factory()
worker = SignalWorker(session_factory)
live = LiveChartManager(session_factory)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await worker.start()
    asyncio.create_task(_renewal_watchdog())
    logger.info("Dashboard ready")
    yield
    await worker.stop()
    await live.shutdown()


app = FastAPI(title="Quotex AI Dashboard", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SUPPORTED_TF = [15, 30, 60, 120, 300, 900, 1800, 3600]


async def _renewal_watchdog():
    """Proactively renew the SSID periodically so the website never hits an expired token."""
    import main as bot_main
    interval = float(os.getenv("DASHBOARD_RENEW_INTERVAL", "1800"))
    while True:
        await asyncio.sleep(interval)
        try:
            logger.info("Auto-renewing SSID (website watchdog)...")
            await bot_main.get_quotex_connection()
        except Exception as e:
            logger.error("Website SSID renewal failed: %s", e)


# ─── auth helpers ────────────────────────────────────────────────────
async def _require_user(request: Request) -> User:
    uid = auth_mod.current_user_id(request)
    if not uid:
        raise HTTPException(status_code=401, detail="Not authenticated")
    async with session_factory() as session:
        user = await session.get(User, uid)
        if not user:
            raise HTTPException(status_code=401, detail="Unknown user")
        return user


# ─── Pydantic models ─────────────────────────────────────────────────
class GoogleLoginIn(BaseModel):
    id_token: str


class DemoLoginIn(BaseModel):
    email: str = ""
    name: str = ""


class SignalIn(BaseModel):
    pair: str
    timeframe_seconds: int = 60
    model_type: str = "llm"  # llm / vision / all


class CheckoutIn(BaseModel):
    plan_id: str


# ─── pages ───────────────────────────────────────────────────────────
@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ─── auth endpoints ──────────────────────────────────────────────────
@app.post("/api/auth/google")
async def google_login(body: GoogleLoginIn, response: Response):
    info = await auth_mod.verify_google_id_token(body.id_token)
    sub = str(info.get("sub"))
    email = str(info.get("email", ""))
    name = str(info.get("name", ""))
    avatar = str(info.get("picture", ""))

    async with session_factory() as session:
        user = await session.execute(__import__("sqlalchemy").select(User).where(User.google_sub == sub))
        user = user.scalar_one_or_none()
        if not user:
            user = User(google_sub=sub, email=email, name=name, avatar=avatar, credits_balance=0.0)
            session.add(user)
            await session.flush()
            # first login grant: 120 free credits
            await credits_mod.grant_topup(session, user, auth_mod.FREE_CREDITS,
                                          reason="FREE plan signup bonus (120 credits)")
            user.free_credits_granted = True
            await session.commit()
        else:
            user.email = email
            user.name = name or user.name
            user.avatar = avatar or user.avatar
            await session.commit()

        auth_mod.set_session_cookie(response, user)
        return {"token_ok": True, "user": _user_out(user)}


@app.post("/api/auth/demo")
async def demo_login(body: DemoLoginIn, response: Response):
    if not auth_mod.demo_enabled():
        raise HTTPException(status_code=403, detail="Demo login disabled")
    email = (body.email or f"demo_{uuid.uuid4().hex[:8]}@demo.local").lower()
    name = body.name or "Demo Trader"
    sub = f"demo_{email}"

    async with session_factory() as session:
        from sqlalchemy import select
        user = (await session.execute(select(User).where(User.google_sub == sub))).scalar_one_or_none()
        if not user:
            user = User(google_sub=sub, email=email, name=name, avatar="",
                        credits_balance=0.0, free_credits_granted=True)
            session.add(user)
            await session.flush()
            await credits_mod.grant_topup(session, user, 1200, reason="Demo signup bonus")
            await session.commit()
        auth_mod.set_session_cookie(response, user)
        return {"token_ok": True, "user": _user_out(user)}


@app.post("/api/auth/logout")
async def logout(response: Response):
    auth_mod.clear_session_cookie(response)
    return {"ok": True}


# ─── data endpoints ──────────────────────────────────────────────────
def _user_out(user: User) -> dict:
    return {
        "id": user.id, "email": user.email, "name": user.name, "avatar": user.avatar,
        "credits": round(user.credits_balance, 2),
        "plan": user.plan_name,
        "plan_credits_per_month": user.plan_credits_per_month,
        "plan_price": user.plan_price,
        "renews_at": user.renews_at.isoformat() if user.renews_at else None,
        "free_credits_granted": user.free_credits_granted,
    }


@app.get("/api/me")
async def me(user: User = Depends(_require_user)):
    return _user_out(user)


@app.get("/api/pairs")
async def pairs(user: User = Depends(_require_user)):
    """Active Quotex pairs grouped OTC / REAL / CRYPTO with payouts."""
    try:
        import main as bot_main
        client = await bot_main.get_quotex_connection()
        active = await bot_main.adapter_get_active_pairs(client)
        groups = {"OTC": [], "REAL": [], "CRYPTO": []}
        for cat, items in active.items():
            groups.setdefault(cat, [])
            for payout, sym in items:
                groups[cat].append({"symbol": sym, "payout": payout,
                                    "label": _pretty_pair(sym)})
        return groups
    except Exception as e:
        logger.warning("pairs fetch failed: %s", e)
        return {"OTC": [], "REAL": [], "CRYPTO": [], "error": str(e)}


@app.get("/api/config")
async def config():
    return {"google_client_id": auth_mod.GOOGLE_CLIENT_ID,
            "demo": auth_mod.demo_enabled(),
            "stripe": billing.stripe_enabled()}


@app.get("/api/demo_mode")
async def demo_mode():
    return {"demo": auth_mod.demo_enabled()}


@app.get("/api/timeframes")
async def timeframes(user: User = Depends(_require_user)):
    return {"timeframes": SUPPORTED_TF,
            "labels": {tf: _tf_label(tf) for tf in SUPPORTED_TF}}


def _tf_label(tf: int) -> str:
    if tf < 60:
        return f"{tf}s"
    m = tf // 60
    return f"{m}m"


def _pretty_pair(symbol: str) -> str:
    s = symbol.replace("_otc", "").upper()
    if len(s) == 6 and not any(c.isdigit() for c in s):
        return f"{s[:3]}/{s[3:]}"
    return s


# ─── signals ─────────────────────────────────────────────────────────
@app.post("/api/signal")
async def create_signal(body: SignalIn, user: User = Depends(_require_user)):
    if body.model_type not in ("llm", "vision", "all"):
        raise HTTPException(status_code=400, detail="model_type must be llm/vision/all")
    if body.timeframe_seconds not in SUPPORTED_TF:
        raise HTTPException(status_code=400, detail="Unsupported timeframe")
    if not body.pair:
        raise HTTPException(status_code=400, detail="pair required")

    cost = credits_mod._get_cost(body.model_type)

    job_id = f"job_{uuid.uuid4().hex[:12]}"
    async with session_factory() as session:
        fresh = await session.get(User, user.id)
        if not fresh:
            raise HTTPException(status_code=401, detail="Unknown user")

        ok, msg = await credits_mod.check_balance(session, fresh, cost)
        if not ok:
            raise HTTPException(status_code=402, detail=msg)

        job = Job(job_id=job_id, user_id=fresh.id, model_type=body.model_type,
                  pair=body.pair, timeframe_seconds=body.timeframe_seconds,
                  status="queued", step=1, progress_text="⏳ Queued — waiting for worker…")
        session.add(job)
        await session.commit()

        reserved = await credits_mod.reserve_credits(session, fresh, cost)
        if not reserved:
            await credits_mod.refund_credits(session, fresh, cost, reason="queue race refund")
            await session.commit()
            raise HTTPException(status_code=402, detail="Insufficient credits")
        else:
            await session.commit()

    worker.enqueue(job_id)
    return {"job_id": job_id, "cost": cost, "status": "queued"}


@app.get("/api/signal/{job_id}")
async def job_status(job_id: str, user: User = Depends(_require_user)):
    from sqlalchemy import select
    async with session_factory() as session:
        job = (await session.execute(select(Job).where(Job.job_id == job_id, Job.user_id == user.id))).scalar_one_or_none()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        result = {}
        if job.result:
            try:
                result = json.loads(job.result)
            except Exception:
                result = {}
        # attach stored chart image + aggregate reasoning so the result card
        # can render the same full detail as the history screen
        sig = (await session.execute(
            select(Signal).where(Signal.job_id == job.job_id)
        )).scalar_one_or_none()
        if sig:
            result["chart_b64"] = sig.chart_b64 or ""
            result["original_pair"] = sig.original_pair or ""
            result["created_at"] = sig.created_at
            result["trade_time"] = sig.trade_time
            result["data_timestamp"] = sig.data_timestamp
            result["trade_result"] = sig.trade_result or ""
            if sig.trade_checked_at:
                result["trade_checked_at"] = sig.trade_checked_at
            if sig.reasoning_json:
                try:
                    result["reasoning"] = json.loads(sig.reasoning_json)
                except Exception:
                    pass
        return {
            "job_id": job.job_id, "status": job.status, "step": job.step,
            "progress_text": job.progress_text, "error": job.error, "result": result,
        }


@app.get("/api/signals")
async def my_signals(limit: int = 25, offset: int = 0, user: User = Depends(_require_user)):
    from sqlalchemy import select
    async with session_factory() as session:
        rows = (await session.execute(
            select(Signal).where(Signal.user_id == user.id)
            .order_by(Signal.created_at.desc()).offset(offset).limit(min(limit, 100))
        )).scalars().all()
        return [{
            "id": s.id, "pair": s.pair, "original_pair": s.original_pair,
            "model_type": s.model_type, "tf_label": s.timeframe_label,
            "timeframe_seconds": s.timeframe_seconds, "direction": s.direction,
            "confidence": s.confidence, "status": s.status,
            "math_score": s.math_score, "credits_cost": s.credits_cost,
            "votes": _json_safe(s.votes_json),
            "created_at": s.created_at,
            "trade_time": s.trade_time,
            "data_timestamp": s.data_timestamp,
            "trade_result": s.trade_result or "",
            "has_chart": bool(s.chart_b64),
        } for s in rows]


@app.get("/api/signal_detail/{signal_id}")
async def signal_detail(signal_id: int, user: User = Depends(_require_user)):
    async with session_factory() as session:
        s = await session.get(Signal, signal_id)
        if not s or s.user_id != user.id:
            raise HTTPException(status_code=404, detail="Not found")
        return {
            "pair": s.pair, "original_pair": s.original_pair, "model_type": s.model_type,
            "tf_label": s.timeframe_label, "direction": s.direction, "confidence": s.confidence,
            "reason": s.reason, "note": s.note, "martingale_recommendation": s.martingale_recommendation,
            "math_score": s.math_score, "status": s.status,
            "votes": _json_safe(s.votes_json),
            "reasoning": _json_safe(s.reasoning_json),
            "chart_b64": s.chart_b64 or "",
            "created_at": s.created_at,
            "trade_time": s.trade_time,
            "data_timestamp": s.data_timestamp,
            "trade_result": s.trade_result or "",
        }


# ─── credits / billing ───────────────────────────────────────────────
@app.get("/api/credits")
async def credit_ledger(user: User = Depends(_require_user)):
    async with session_factory() as session:
        fresh = await session.get(User, user.id)
        ledger = await credits_mod.get_ledger(session, user.id, limit=200)
        return {"balance": round(fresh.credits_balance, 2), "ledger": ledger}


@app.get("/api/plans")
async def plans():
    return billing.PLANS


@app.post("/api/checkout")
async def checkout(body: CheckoutIn, user: User = Depends(_require_user)):
    try:
        chk = await billing.create_checkout(user, body.plan_id)
        return chk
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/checkout/mock/complete")
async def complete_mock(body: CheckoutIn, user: User = Depends(_require_user)):
    if billing.stripe_enabled():
        raise HTTPException(status_code=400, detail="Mock checkout disabled when Stripe is configured")
    async with session_factory() as session:
        fresh = await session.get(User, user.id)
        await billing.complete_mock_checkout(session, fresh, body.plan_id)
        await session.commit()
        return _user_out(fresh)


@app.post("/api/stripe/webhook")
async def stripe_webhook(request: Request):
    """Production webhook — out of scope until real Stripe keys are set."""
    raise HTTPException(status_code=501, detail="Stripe webhook not configured")


# ─── live chart ──────────────────────────────────────────────────────
@app.websocket("/api/live")
async def live_ws(ws: WebSocket):
    await ws.accept()
    try:
        token = ws.cookies.get(auth_mod.COOKIE_NAME)
        sess = auth_mod.decode_session(token)
        if not sess:
            await ws.send_json({"type": "error", "msg": "Not authenticated"})
            await ws.close(code=4401)
            return
        await live.handle(ws, user_id=sess.get("uid"))
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("live ws error: %s", e)


# ─── health ──────────────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    return {"ok": True, "time": datetime.now(timezone.utc).isoformat()}


def _json_safe(s) -> list | dict:
    if not s:
        return [] if isinstance(s, str) else s
    try:
        return json.loads(s)
    except Exception:
        return {}