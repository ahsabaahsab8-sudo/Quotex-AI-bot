"""Signal worker — single asyncio consumer of the job queue.

Runs the exact 5-step pipeline the Telegram bot uses, but with live per-step
progress + per-model vote details for the website UI.

Step 1: Connect to Quotex (SSID, renews if needed)
Step 2: Fetch candles + 20-factor indicator computation
Step 3: Analyze market (math score, auto-scan best pair if weak)
Step 4: Check news / build the AI context block
Step 5: Run the 3-model (or 6-model) AI vote in parallel

After the signal is stored the bot-style WIN/LOSS check runs in the
background: it waits for the current candle to close plus one full candle,
then fetches the last candles and marks the signal WIN or LOSS.
"""
import asyncio
import json
import logging
import os
import time as _time
from datetime import datetime, timezone, timedelta
from sqlalchemy import select

from .database import Job, Signal, User
import main as bot_main
from . import credits as credits_mod
from .vote import run_model_vote

logger = logging.getLogger(__name__)

PKT = timezone(timedelta(hours=5))


def _trade_meta(candles, tf: int) -> dict:
    """Bot-style timing metadata (same math as format_telegram_signal)."""
    now_ts = datetime.now(PKT).timestamp()
    elapsed = int(now_ts % tf)
    remaining = tf - elapsed
    if remaining == tf:
        remaining = 0
    candle_start = now_ts - elapsed
    next_start = candle_start + tf
    data_ts = None
    if candles:
        for c in reversed(candles):
            t = c.get("time")
            if t:
                data_ts = float(t)
                break
    def _fmt(ts):
        return datetime.fromtimestamp(ts, tz=PKT).strftime("%H:%M:%S")
    return {
        "data_timestamp": data_ts,
        "trade_time": _fmt(next_start),
        "candle_start": _fmt(candle_start),
        "countdown": remaining,
    }


class SignalWorker:
    def __init__(self, session_factory):
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=32)
        self._session_factory = session_factory
        self._task: asyncio.Task | None = None

    def enqueue(self, job_id: str):
        self._queue.put_nowait(job_id)

    async def start(self):
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self):
        while True:
            job_id = await self._queue.get()
            try:
                await self._process(job_id)
            except Exception as e:
                logger.exception("Job %s crashed", job_id)
                await self._fail(job_id, str(e))
            finally:
                self._queue.task_done()

    async def _update_job(self, session, job: Job, **kw):
        for k, v in kw.items():
            setattr(job, k, v)
        job.updated_at = datetime.now(timezone.utc)
        await session.commit()

    async def _fail(self, job_id: str, error: str):
        from sqlalchemy import select
        async with self._session_factory() as session:
            job = (await session.execute(select(Job).where(Job.job_id == job_id))).scalar_one_or_none()
            if not job:
                return
            user = await session.get(User, job.user_id)
            cost = credits_mod._get_cost(job.model_type)
            job.status = "failed"
            job.error = error[:2000]
            await session.commit()
            if user and cost > 0:
                await credits_mod.refund_credits(session, user, cost, reason=f"refund failed signal {job.pair}")
                await session.commit()

    async def _process(self, job_id: str):
        from sqlalchemy import select
        async with self._session_factory() as session:
            job = (await session.execute(select(Job).where(Job.job_id == job_id))).scalar_one_or_none()
            if not job:
                return
            user = await session.get(User, job.user_id)
            if not user:
                return
            cost = credits_mod._get_cost(job.model_type)

            await self._update_job(session, job, status="running", step=1,
                                   progress_text="📊 Step 1/5: Connecting to Quotex (checking SSID…)")

            client = None
            try:
                client = await bot_main.get_quotex_connection()
                await self._update_job(session, job, step=2,
                                       progress_text="📈 Step 2/5: Fetching market data + computing indicators…")

                tech_data = await bot_main.fetch_and_process_indicators(
                    client, job.pair, timeframe=job.timeframe_seconds
                )
                if tech_data is None:
                    raise RuntimeError(f"Failed to fetch candle data for {job.pair}")
                if tech_data == "LOW_VOLATILITY":
                    job.result = json.dumps({"job_id": job.job_id, "direction": "SKIP",
                                             "skipped": True, "pair": job.pair,
                                             "reason": f"{job.pair} has LOW VOLATILITY right now — no reliable signal."})
                    await self._update_job(session, job, status="done", step=2,
                                           progress_text="⚠️ Low volatility — no reliable signal.")
                    await self._refund_and_record_skip(session, job, user, cost, reason="Low volatility — no reliable signal.")
                    return

                summary = tech_data["summary"]
                candles = tech_data["candles"]
                n_candles = len(candles) if candles else 0
                tf_label = bot_main.format_timeframe_label(job.timeframe_seconds)
                await self._update_job(session, job, step=3,
                                       progress_text=f"🧠 Step 3/5: Analyzing market — {n_candles} {tf_label} candles, indicators OK. Math scoring…")

                math_score = bot_main.score_pair_math(summary)
                final_pair = job.pair
                original_pair = job.pair
                auto_switch_note = ""

                if math_score < 7.0:
                    await self._update_job(session, job, step=3,
                                           progress_text=f"🎯 Step 3/5: {job.pair} scores {math_score}/10 (weak). Auto-scanning category…")
                    cat = bot_main.get_pair_category(job.pair)
                    active_pairs = await bot_main.adapter_get_active_pairs(client)
                    cat_pairs = active_pairs.get(cat, [])
                    best = await bot_main.auto_scan_best_pair(client, cat, cat_pairs, timeframe=job.timeframe_seconds)
                    if best and best["math_score"] > math_score:
                        final_pair = best["code"]
                        math_score = best["math_score"]
                        tech_data = best["tech_data"]
                        summary = tech_data["summary"]
                        candles = tech_data["candles"]
                        auto_switch_note = f"Auto-selected {final_pair} (score {math_score:.1f}/10) for a stronger setup."

                await self._update_job(session, job, step=4,
                                       progress_text="🗞️ Step 4/5: Checking news + building the AI analysis context…")

                chart_b64 = None
                if job.model_type in ("vision", "all"):
                    chart_b64 = await self._render_chart(candles, summary, final_pair, job.timeframe_seconds)
                    await self._update_job(session, job, step=5,
                                           progress_text="🤖 Step 5/5: Running 3-stage AI vote (Vision models)…")

                if job.model_type == "all":
                    await self._update_job(session, job, step=5,
                                           progress_text="🤖 Step 5/5: Running ALL 6 models (Vision + LLM combined vote)…")
                    vote_ctx = await run_model_vote(
                        summary=summary, pair_code=final_pair, mode="all", chart_b64=chart_b64,
                    )
                    await self._store_result(session, job, user, cost, vote_ctx,
                                             model_type="all", pair=final_pair,
                                             original_pair=original_pair if final_pair != original_pair else None,
                                             tf_label=tf_label, math_score=math_score,
                                             chart_b64=chart_b64, note=auto_switch_note,
                                             candles=candles)
                elif job.model_type == "vision":
                    vote_ctx = await run_model_vote(
                        summary=summary, pair_code=final_pair, mode="vision", chart_b64=chart_b64,
                    )
                    await self._store_result(session, job, user, cost, vote_ctx,
                                             model_type="vision", pair=final_pair,
                                             original_pair=original_pair if final_pair != original_pair else None,
                                             tf_label=tf_label, math_score=math_score,
                                             chart_b64=chart_b64, note=auto_switch_note,
                                             candles=candles)
                else:  # llm
                    await self._update_job(session, job, step=5,
                                           progress_text="🤖 Step 5/5: Running 3-stage AI vote (LLM models)…")
                    vote_ctx = await run_model_vote(
                        summary=summary, pair_code=final_pair, mode="llm", chart_b64=None,
                    )
                    await self._store_result(session, job, user, cost, vote_ctx,
                                             model_type="llm", pair=final_pair,
                                             original_pair=original_pair if final_pair != original_pair else None,
                                             tf_label=tf_label, math_score=math_score,
                                             chart_b64=None, note=auto_switch_note,
                                             candles=candles)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.exception("Signal job %s failed", job_id)
                await self._update_job(session, job, status="failed", error=str(e))
                await credits_mod.refund_credits(session, user, cost, reason=f"refund failed signal {job.pair}")
                await session.commit()
            finally:
                try:
                    if client is not None:
                        await bot_main.close_quotex_connection()
                except Exception:
                    pass

    async def _render_chart(self, candles, summary, pair, tf):
        if not candles:
            return None
        try:
            import chart_render
            return await asyncio.to_thread(
                chart_render.render_chart_to_base64,
                candles, summary=summary, token=pair, timeframe=tf,
            )
        except Exception as e:
            logger.warning("Chart render failed for %s: %s", pair, e)
            return None

    async def _refund_and_record_skip(self, session, job, user, cost, reason):
        sig = Signal(
            user_id=user.id, job_id=job.job_id, model_type=job.model_type,
            pair=job.pair, original_pair=job.pair,
            timeframe_seconds=job.timeframe_seconds,
            timeframe_label=bot_main.format_timeframe_label(job.timeframe_seconds),
            reason=reason, status="skipped", credits_cost=0.0,
        )
        session.add(sig)
        await credits_mod.refund_credits(session, user, cost, reason=f"refund no-signal {job.pair}")
        await session.commit()
        try:
            await bot_main.close_quotex_connection()
        except Exception:
            pass

    async def _store_result(self, session, job, user, cost, vote_ctx, model_type,
                            pair, original_pair, tf_label, math_score, chart_b64, note,
                            candles=None):
        direction = vote_ctx["direction"]
        confidence = vote_ctx["confidence"]
        made_skip = direction in ("SKIP", "NONE", "NEUTRAL")

        meta = _trade_meta(candles or [], job.timeframe_seconds)

        sig = Signal(
            user_id=user.id, job_id=job.job_id, model_type=model_type,
            pair=pair, original_pair=original_pair or "",
            timeframe_seconds=job.timeframe_seconds, timeframe_label=tf_label,
            payout=vote_ctx.get("payout", 80),
            direction=direction, confidence=confidence,
            reason=vote_ctx.get("reason", ""),
            note=note,
            martingale_recommendation=vote_ctx.get("martingale_recommendation", "M0"),
            votes_json=json.dumps(vote_ctx.get("votes") or []),
            reasoning_json=json.dumps(vote_ctx.get("reasoning") or {}),
            chart_b64=chart_b64 or "",
            math_score=math_score,
            credits_cost=cost,
            status="skipped" if made_skip else "done",
            data_timestamp=meta["data_timestamp"],
            trade_time=meta["trade_time"],
        )
        session.add(sig)
        await session.flush()

        await credits_mod.confirm_deduction(session, user, cost,
                                            reason=f"signal {pair} {tf_label} ({model_type})",
                                            signal_id=sig.id)

        result = {
            "job_id": job.job_id,
            "direction": direction,
            "confidence": confidence,
            "reason": vote_ctx.get("reason", ""),
            "note": note,
            "martingale_recommendation": vote_ctx.get("martingale_recommendation", "M0"),
            "votes": vote_ctx.get("votes") or [],
            "model_type": model_type,
            "pair": pair,
            "tf_label": tf_label,
            "timeframe_seconds": job.timeframe_seconds,
            "math_score": math_score,
            "has_chart": bool(chart_b64),
            "skipped": made_skip,
            "trade_time": meta["trade_time"],
            "candle_start": meta["candle_start"],
            "countdown": meta["countdown"],
            "data_timestamp": meta["data_timestamp"],
        }
        job.result = json.dumps(result)
        job.status = "skipped" if made_skip else "done"
        job.step = 5
        job.progress_text = "✅ Signal ready" if not made_skip else "⏭️ No signal (skipped)"
        await session.commit()

        if not made_skip:
            asyncio.get_running_loop().create_task(
                self._check_trade_result(job.job_id, sig.id, pair,
                                         job.timeframe_seconds, direction)
            )

    async def _check_trade_result(self, job_id: str, signal_id: int, pair: str, tf: int, direction: str):
        """Bot-style WIN/LOSS: wait for current candle end + next full candle, then inspect last closed candle."""
        try:
            now_ts = datetime.now(PKT).timestamp()
            remaining = tf - int(now_ts % tf)
            if remaining == tf:
                remaining = tf
            await asyncio.sleep(remaining + tf)

            client = await bot_main.adapter_get_quotex_connection()
            try:
                candles = await bot_main.adapter_fetch_candles(
                    client, pair, count=tf * 10 + 60, timeframe=tf)
            finally:
                try:
                    await bot_main.close_quotex_connection()
                except Exception:
                    pass

            if not candles or len(candles) < 2:
                return
            c = candles[-2]
            c_open = float(c["open"])
            c_close = float(c["close"])
            went_up = c_close > c_open
            predicted_up = direction == "BUY"
            won = went_up == predicted_up
            trade_result = "WIN" if won else "LOSS"

            async with self._session_factory() as session:
                sig = await session.get(Signal, signal_id)
                if sig and sig.status != "skipped":
                    sig.trade_result = trade_result
                    sig.trade_checked_at = datetime.now(timezone.utc)
                    await session.commit()
                    logger.info("Signal %s %s: %s (open=%s close=%s)", job_id, pair, trade_result, c_open, c_close)
        except Exception as e:
            logger.warning("Trade result check failed for %s: %s", job_id, e)