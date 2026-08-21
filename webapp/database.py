"""SQLite database (SQLAlchemy async) for the Quotex AI dashboard."""
import os
import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import (
    String, Integer, Float, Boolean, Text, DateTime, ForeignKey, UniqueConstraint,
)

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "webapp", "dashboard.db")
DB_URL = os.getenv("DASHBOARD_DB_URL", f"sqlite+aiosqlite:///{DB_PATH}")


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ─── USERS ────────────────────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    google_sub: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    avatar: Mapped[str] = mapped_column(String(1024), default="")
    credits_balance: Mapped[float] = mapped_column(Float, default=0.0)
    free_credits_granted: Mapped[bool] = mapped_column(Boolean, default=False)
    plan_name: Mapped[str] = mapped_column(String(32), default="FREE")
    plan_credits_per_month: Mapped[float] = mapped_column(Float, default=0.0)
    plan_price: Mapped[float] = mapped_column(Float, default=0.0)
    renews_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    stripe_customer_id: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (UniqueConstraint("google_sub", name="uq_user_google_sub"),)


# ─── CREDIT TRANSACTIONS (the ledger) ────────────────────────────────
class CreditTransaction(Base):
    __tablename__ = "credit_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    amount: Mapped[float] = mapped_column(Float)  # +top-up / -signal cost
    reason: Mapped[str] = mapped_column(String(255))
    signal_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# ─── SUBSCRIPTION PLANS ──────────────────────────────────────────────
class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(32))
    credits_per_month: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    renews_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active/cancelled
    stripe_session_id: Mapped[str] = mapped_column(String(255), default="")


# ─── SIGNALS ─────────────────────────────────────────────────────────
class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    job_id: Mapped[str] = mapped_column(String(64), index=True)
    model_type: Mapped[str] = mapped_column(String(16))  # llm / vision / all
    pair: Mapped[str] = mapped_column(String(32))
    original_pair: Mapped[str] = mapped_column(String(32), default="")
    timeframe_seconds: Mapped[int] = mapped_column(Integer)
    timeframe_label: Mapped[str] = mapped_column(String(8))
    payout: Mapped[int] = mapped_column(Integer, default=80)
    direction: Mapped[str] = mapped_column(String(8), default="")       # BUY / SELL
    confidence: Mapped[int] = mapped_column(Integer, default=0)
    reason: Mapped[str] = mapped_column(Text, default="")
    note: Mapped[str] = mapped_column(String(500), default="")
    martingale_recommendation: Mapped[str] = mapped_column(String(4), default="M0")
    votes_json: Mapped[str] = mapped_column(Text, default="[]")        # per-model details
    reasoning_json: Mapped[str] = mapped_column(Text, default="{}")
    chart_b64: Mapped[str] = mapped_column(Text, default="")           # vision only
    math_score: Mapped[float] = mapped_column(Float, default=0.0)
    credits_cost: Mapped[float] = mapped_column(Float, default=10.0)
    status: Mapped[str] = mapped_column(String(16), default="done")    # done / skipped / failed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    data_timestamp: Mapped[float | None] = mapped_column(Float, nullable=True)  # newest closed candle epoch (PKT-safe)
    trade_time: Mapped[str] = mapped_column(String(32), default="")    # next candle start "HH:MM:SS" (PKT)
    trade_result: Mapped[str] = mapped_column(String(8), default="")   # WIN / LOSS / PENDING / ""
    trade_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (UniqueConstraint("job_id", name="uq_signal_job"),)


# ─── SIGNAL JOBS (queue visibility for the frontend) ─────────────────
class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    model_type: Mapped[str] = mapped_column(String(16))
    pair: Mapped[str] = mapped_column(String(32))
    timeframe_seconds: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued/running/done/failed/cancelled
    step: Mapped[int] = mapped_column(Integer, default=1)              # 1..5
    progress_text: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[str] = mapped_column(Text, default="{}")            # JSON signal summary
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


async def init_db():
    from sqlalchemy.ext.asyncio import async_engine_from_config

    engine = create_async_engine(DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _migrate(engine)
    await engine.dispose()
    logger.info("Database ready: %s", DB_PATH)


async def _migrate(engine):
    from sqlalchemy import text
    for table, cols in _MIGRATE_COLS.items():
        async with engine.begin() as conn:
            res = await conn.execute(text(f"PRAGMA table_info({table})"))
            existing = {row[1].lower() for row in res.fetchall()}
            for name, typ in cols:
                if name not in existing:
                    await conn.execute(text(
                        f"ALTER TABLE {table} ADD COLUMN {name} {typ}"))


_MIGRATE_COLS = {
    "signals": [
        ("data_timestamp", "FLOAT"),
        ("trade_time", "VARCHAR(32)"),
        ("trade_result", "VARCHAR(8)"),
        ("trade_checked_at", "DATETIME"),
    ],
}


def make_session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(DB_URL, echo=False)
    return async_sessionmaker(engine, expire_on_commit=False)