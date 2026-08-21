"""Pricing plans + checkout (real Stripe when configured, mock for localhost)."""
import os
import logging

from .database import User, Subscription
from . import credits as credits_mod

logger = logging.getLogger(__name__)

PLANS = [
    {
        "id": "free",
        "name": "Free",
        "price": 0,
        "credits_per_month": 120,
        "recurring": False,
        "features": ["120 credits on signup", "Vision + LLM signals", "10 credits per signal", "Live chart (basic)"],
    },
    {
        "id": "starter",
        "name": "Starter",
        "price": 20,
        "credits_per_month": 2000,
        "recurring": True,
        "features": ["2,000 credits / month", "~200 signals", "Premium live chart", "Full history", "Telegram bot access"],
    },
    {
        "id": "pro",
        "name": "Pro",
        "price": 100,
        "credits_per_month": 40000,
        "recurring": True,
        "features": ["40,000 credits / month", "~4,000 signals", "UNLIMITED vision + LLM", "All 6 models combined vote", "VIP priority queue", "Telegram bot access"],
    },
]

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")


def stripe_enabled() -> bool:
    return bool(STRIPE_SECRET_KEY)


async def get_plan(plan_id: str) -> dict | None:
    for p in PLANS:
        if p["id"] == plan_id:
            return p
    return None


async def apply_plan(session, user: User, plan: dict, months: int = 1):
    """Grant monthly credits + update the user's plan row (idempotent upgrader)."""
    was_free = user.plan_name in ("FREE", "free")
    user.plan_name = plan["id"].upper()
    user.plan_credits_per_month = plan["credits_per_month"]
    user.plan_price = plan["price"]

    from datetime import datetime, timedelta, timezone
    from .database import utcnow

    now = utcnow()
    base = user.renews_at if (user.renews_at and user.renews_at > now and not was_free) else now
    user.renews_at = base + timedelta(days=30 * months)
    await credits_mod.grant_topup(session, user, plan["credits_per_month"] * months,
                                  reason=f"{plan['name']} plan top-up ({plan['credits_per_month']*months} credits)")

    sub = Subscription(
        user_id=user.id, name=plan["name"], credits_per_month=plan["credits_per_month"],
        price=plan["price"], started_at=now, renews_at=user.renews_at, status="active",
    )
    session.add(sub)
    await session.flush()
    logger.info("Plan %s applied to user %s", plan["id"], user.id)


async def create_checkout(user: User, plan_id: str) -> dict:
    """Return a checkout URL. Uses Stripe Checkout if keys are set, otherwise a
    mock flow that completes instantly (for localhost testing)."""
    plan = await get_plan(plan_id)
    if not plan:
        raise ValueError("Unknown plan")
    if plan["price"] <= 0:
        raise ValueError("Free plan needs no checkout")

    if stripe_enabled():
        import stripe
        stripe.api_key = STRIPE_SECRET_KEY
        success_url = os.getenv("DASHBOARD_BASE_URL", "http://localhost:8000") + "/credits?checkout=success"
        cancel_url = os.getenv("DASHBOARD_BASE_URL", "http://localhost:8000") + "/pricing?checkout=cancelled"
        session = stripe.checkout.Session.create(
            mode="subscription" if plan["recurring"] else "payment",
            customer_email=user.email,
            line_items=[{"price": plan["stripe_price_id"], "quantity": 1}],
            success_url=success_url, cancel_url=cancel_url,
            metadata={"user_id": str(user.id), "plan_id": plan_id},
        )
        return {"mode": "stripe", "url": session.url, "session_id": session.id}
    else:
        return {"mode": "mock", "url": None, "session_id": f"mock_{plan_id}_{user.id}", "plan": plan}


async def complete_mock_checkout(session, user: User, plan_id: str):
    plan = await get_plan(plan_id)
    if not plan:
        raise ValueError("Unknown plan")
    await apply_plan(session, user, plan, months=1)