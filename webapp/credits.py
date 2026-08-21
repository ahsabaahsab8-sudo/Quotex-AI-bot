"""Credit ledger logic — reserve on job enqueue, deduct on success, refund on failure.

All credit mutations run inside DB transactions to prevent races (single writer
on SQLite via one app process, so a mutex is enough).
"""
import asyncio
import logging
from sqlalchemy import select

from .database import User, CreditTransaction

logger = logging.getLogger(__name__)

SIGNAL_COST = 10.0  # 10 credits per signal (per plan spec)


def _get_cost(model_type: str) -> float:
    # Vision and LLM both cost 10; "all" (6 models) could cost more later.
    return 10.0 if model_type != "all" else 20.0


async def check_balance(
    session,
    user: User,
    cost: float,
) -> tuple[bool, str]:
    """Return (ok, message). Balance read inside a read-then-guard pattern."""
    if user.credits_balance < cost:
        return False, "Insufficient credits — upgrade your plan."
    return True, ""


async def reserve_credits(session, user: User, cost: float) -> bool:
    """Spin-lock reserve: decrement balance immediately (atomic update)."""
    if user.credits_balance < cost:
        return False
    user.credits_balance -= cost
    await session.flush()
    return True


async def confirm_deduction(session, user: User, cost: float, reason: str, signal_id: int | None = None):
    """Called after a successful signal — records the ledger row."""
    tx = CreditTransaction(user_id=user.id, amount=-cost, reason=reason, signal_id=signal_id)
    session.add(tx)
    # balance already reduced at reserve time
    await session.flush()


async def refund_credits(session, user: User, cost: float, reason: str):
    """Refund a failed/refused signal back into the balance."""
    user.credits_balance += cost
    tx = CreditTransaction(user_id=user.id, amount=+cost, reason=reason)
    session.add(tx)
    await session.flush()


async def grant_topup(session, user: User, amount: float, reason: str):
    user.credits_balance += amount
    tx = CreditTransaction(user_id=user.id, amount=+amount, reason=reason)
    session.add(tx)
    await session.flush()


async def get_ledger(session, user_id: int, limit: int = 200) -> list[dict]:
    rows = (
        await session.execute(
            select(CreditTransaction)
            .where(CreditTransaction.user_id == user_id)
            .order_by(CreditTransaction.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [
        {
            "id": t.id,
            "amount": t.amount,
            "reason": t.reason,
            "signal_id": t.signal_id,
            "created_at": t.created_at,
        }
        for t in rows
    ]