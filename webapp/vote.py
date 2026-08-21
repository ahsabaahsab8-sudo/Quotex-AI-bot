"""Parallel model vote — mirrors main.py's query_all_models / query_all_llm_models
majority logic but captures full per-model responses so the dashboard can render
vote cards + expandable reasoning.

Runs the SAME underlying query functions the Telegram bot uses (same prompts,
same keys, same timeouts), so behavior is identical.
"""
import asyncio
import json
import logging

import main as bot_main

logger = logging.getLogger(__name__)


def _normalise_direction(raw) -> str:
    d = str(raw or "").strip().upper()
    if d in ("BUY", "UP"):
        return "BUY"
    if d in ("SELL", "DOWN"):
        return "SELL"
    if d in ("SKIP", "NONE", "NEUTRAL"):
        return "SKIP"
    return "SKIP"


def _safe_int(v, default=50) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


async def _guarded(name, coro, timeout):
    try:
        res = await asyncio.wait_for(coro, timeout=timeout)
        if res is None:
            logger.warning("%s returned nothing", name)
            return name, None
        return name, res
    except asyncio.TimeoutError:
        logger.warning("%s timed out after %ss", name, timeout)
        return name, None
    except Exception as e:
        logger.warning("%s failed: %s", name, e)
        return name, None


def _model_vote_from_response(name, res) -> dict | None:
    if not isinstance(res, dict):
        return None
    direction = _normalise_direction(res.get("direction"))
    if direction == "SKIP":
        # Still capture it so the UI shows a skip, but it doesn't strengthen a side.
        return {
            "model": name, "sign": "SKIP", "direction": "SKIP",
            "confidence": 0, "reason": res.get("reason", ""),
            "chain_of_thought": res.get("chain_of_thought_reasoning") or {},
            "analysis": res.get("analysis") or {},
            "chart_analysis": res.get("chart_analysis") or {},
            "martingale": res.get("martingale_recommendation", "M0"),
            "raw": res,
        }
    confidence = _safe_int(res.get("confidence"), 50)
    return {
        "model": name, "sign": direction, "direction": direction,
        "confidence": max(0, min(100, confidence)),
        "reason": res.get("reason", ""),
        "chain_of_thought": res.get("chain_of_thought_reasoning") or {},
        "analysis": res.get("analysis") or {},
        "chart_analysis": res.get("chart_analysis") or {},
        "martingale": res.get("martingale_recommendation", "M0"),
        "raw": res,
    }


async def run_model_vote(summary: dict, pair_code: str = "", mode: str = "vision",
                         chart_b64: str | None = None) -> dict:
    """mode: 'vision' | 'llm' | 'all'

    Returns:
      direction, confidence, reason, votes (per-model), reasoning (aggregate),
      martingale_recommendation, payout.
    """
    logger.info("[web dashboard] Running %s vote for %s", mode, pair_code)

    timeout = bot_main.AI_MODEL_TIMEOUT_SECONDS
    deadline = bot_main.AI_VOTE_DEADLINE_SECONDS
    coros = {}

    if mode in ("vision", "all"):
        if bot_main.CHART_MODEL == "gemini":
            label = "Gemini Flash"
            core = bot_main.query_gemini_flash_analysis(summary, chart_b64=chart_b64)
        else:
            label = "Step 3.7 Flash"
            core = bot_main.query_kilo_step_analysis(summary, chart_b64=chart_b64)
        coros[label] = _guarded(label, core, timeout)
        coros["Nemotron 3 Nano"] = _guarded(
            "Nemotron 3 Nano", bot_main.query_nemotron_nano_vote(summary, chart_b64=chart_b64), timeout)
        coros["Dots3-Note"] = _guarded(
            "Dots3-Note", bot_main.query_dots_note_vote(summary, chart_b64=chart_b64), timeout)

    if mode == "llm":
        timeout = bot_main.LLM_MODEL_TIMEOUT_SECONDS
        deadline = bot_main.LLM_VOTE_DEADLINE_SECONDS
        coros["Nemotron 3 Ultra"] = _guarded(
            "Nemotron 3 Ultra", bot_main.query_llm_nemotron_ultra(summary), timeout)
        coros["Llama 3.1 8B"] = _guarded(
            "Llama 3.1 8B", bot_main.query_llm_nvidia_nemotron(summary), timeout)
        coros["Laguna-S 2.1"] = _guarded(
            "Laguna-S 2.1", bot_main.query_llm_kilo_ling(summary), timeout)

    if mode == "all":
        timeout = max(bot_main.LLM_MODEL_TIMEOUT_SECONDS, bot_main.AI_MODEL_TIMEOUT_SECONDS)
        deadline = max(bot_main.LLM_VOTE_DEADLINE_SECONDS, bot_main.AI_VOTE_DEADLINE_SECONDS)
        coros["Nemotron 3 Ultra"] = _guarded(
            "Nemotron 3 Ultra", bot_main.query_llm_nemotron_ultra(summary), timeout)
        coros["Llama 3.1 8B"] = _guarded(
            "Llama 3.1 8B", bot_main.query_llm_nvidia_nemotron(summary), timeout)
        coros["Laguna-S 2.1"] = _guarded(
            "Laguna-S 2.1", bot_main.query_llm_kilo_ling(summary), timeout)

    pending = {asyncio.ensure_future(c): name for name, c in coros.items()}

    votes = {"BUY": 0, "SELL": 0}
    model_votes: list[dict] = []
    confidences: list[int] = []
    reasons: list[str] = []

    loop = asyncio.get_running_loop()
    end = loop.time() + deadline

    while pending:
        remaining = end - loop.time()
        if remaining <= 0:
            break
        done, _ = await asyncio.wait(pending, timeout=remaining, return_when=asyncio.FIRST_COMPLETED)
        for fut in done:
            name, res = fut.result()
            pending.pop(fut, None)
            vote = _model_vote_from_response(name, res)
            if not vote:
                continue
            model_votes.append(vote)
            if vote["sign"] in ("BUY", "SELL"):
                votes[vote["sign"]] += 1
                confidences.append(vote["confidence"])
                reasons.append(f"{name}: {vote['sign']} ({vote['confidence']}%) — {vote['reason']}")
            else:
                reasons.append(f"{name}: SKIP — {vote['reason']}")
        if votes["BUY"] >= 2 or votes["SELL"] >= 2:
            logger.info("Majority reached on %s vote", mode)
            break

    for fut in pending:
        fut.cancel()

    if votes["BUY"] >= 2:
        direction = "BUY"
    elif votes["SELL"] >= 2:
        direction = "SELL"
    elif votes["BUY"] == votes["SELL"] and (votes["BUY"] > 0 or votes["SELL"] > 0):
        direction = "SKIP"  # split 1-1 — don't force a direction
    elif votes["BUY"] > votes["SELL"]:
        direction = "BUY"
    elif votes["SELL"] > votes["BUY"]:
        direction = "SELL"
    else:
        direction = "SKIP"

    avg_conf = int(sum(confidences) / len(confidences)) if confidences else 60
    confidence = max(50, min(95, avg_conf)) if direction != "SKIP" else 0

    sorted_votes = sorted(model_votes, key=lambda v: (-v["confidence"] if v["sign"] != "SKIP" else -1))
    reasoning = {
        "combined": "\n".join(reasons),
        "per_model": sorted_votes,
    }

    logger.info("[web dashboard] %s vote result: BUY=%s SELL=%s -> %s (%s%%)",
                mode, votes["BUY"], votes["SELL"], direction, confidence)

    return {
        "direction": direction,
        "confidence": confidence,
        "reason": "\n".join(reasons),
        "votes": sorted_votes,
        "reasoning": reasoning,
        "tally": {"BUY": votes["BUY"], "SELL": votes["SELL"]},
        "martingale_recommendation": "M1" if confidence >= 75 else "M0",
    }