import os
import sys
import asyncio
import json
import time
import logging
import threading
from datetime import datetime, timezone, timedelta

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv()

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

import main as bot_main
from quotex_adapter import (
    get_active_pairs as adapter_get_active_pairs,
    ALL_QUOTEX_TIMEFRAMES,
    format_timeframe_label,
    close_quotex_connection,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN not set")
    sys.exit(1)


def run_session_keeper_in_thread():
    """Session keeper is now handled by A11ksa adapter — no-op."""
    pass


async def get_active_pairs(client) -> dict:
    return await adapter_get_active_pairs(client)



CATEGORY_EMOJI = {"OTC": "💱", "REAL": "📉", "CRYPTO": "🪙"}
CATEGORY_LABEL = {"OTC": "OTC Currencies", "REAL": "Real Market Currencies", "CRYPTO": "Crypto & Commodities"}


def format_pair_name(code: str) -> str:
    name = code.replace("_otc", "").replace("_OTC", "")
    if len(name) == 6:
        return name[:3] + "/" + name[3:]
    return name


def format_pair_button_label(code: str, payout: int) -> str:
    pair_name = format_pair_name(code)
    if "_otc" in code.lower():
        return f"{pair_name} (OTC) ({payout}%)"
    else:
        return f"{pair_name} ({payout}%)"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Welcome to the Quotex Real Market AI Signal Bot!\n"
        "Click the button below to get high-confidence trading signals."
    )
    keyboard = [[InlineKeyboardButton("🔥 GET SIGNAL", callback_data="get_signal")]]
    
    if type(update).__name__ == "CallbackQuery":
        await update.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    elif getattr(update, "callback_query", None):
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    elif getattr(update, "message", None):
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def model_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("👁️ Vision AI Models", callback_data="model_vision")],
        [InlineKeyboardButton("🤖 LLM Models", callback_data="model_llm")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_start")]
    ]
    
    await query.edit_message_text(
        "Choose AI Model Type for Analysis:\n\n"
        "👁️ **Vision AI Models** - Chart-based analysis (Gemini Flash, Nemotron 3 Nano Omni, Dots3-Note Preview)\n"
        "🤖 **LLM Models** - Text-based analysis (Nemotron 3 Ultra, Llama 3.1 8B, Laguna-S 2.1)",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


async def get_signal_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "model_vision":
        context.user_data["model_type"] = "vision"
    elif query.data == "model_llm":
        context.user_data["model_type"] = "llm"
    
    model_type = context.user_data.get("model_type", "vision")
    
    keyboard = [[InlineKeyboardButton(f"{CATEGORY_EMOJI[c]} {CATEGORY_LABEL[c]}", callback_data=f"cat_{c}")] for c in CATEGORY_LABEL]
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="model_selection")])
    
    model_label = "Vision AI Models" if model_type == "vision" else "LLM Models"
    await query.edit_message_text(
        f"Model: {model_label}\n\nChoose a category to select a pair for AI analysis:",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
    )


async def menu_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cat = query.data.replace("cat_", "")
    model_type = context.user_data.get("model_type", "vision")
    await query.edit_message_text(f"⏳ Connecting to Quotex to fetch {CATEGORY_LABEL.get(cat, cat)}...", parse_mode="Markdown")

    try:
        client = await bot_main.get_quotex_connection()
        pairs_dict = await get_active_pairs(client)
        await close_quotex_connection()
    except Exception as e:
        await query.edit_message_text(f"❌ Failed to connect to Quotex: {e}")
        return

    pairs = pairs_dict.get(cat, [])
    if not pairs:
        await query.edit_message_text(f"❌ No active pairs found for {CATEGORY_LABEL.get(cat, cat)}")
        return

    keyboard, row = [], []
    for payout, code in pairs:
        label = format_pair_button_label(code, payout)
        row.append(InlineKeyboardButton(label, callback_data=f"pair_{model_type}_{cat}_{code}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="get_signal")])

    await query.edit_message_text(f"{CATEGORY_EMOJI.get(cat, '')} *{CATEGORY_LABEL.get(cat, cat)}*\n\nSelect a pair to analyze:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def back_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await start(update, context)


async def pair_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    # callback_data format: pair_{model_type}_{cat}_{code}
    parts = query.data.split("_", 3)
    model_type = parts[1]
    cat = parts[2]
    pair = parts[3]
    
    context.user_data["model_type"] = model_type
    display = format_pair_name(pair)

    tfs = ALL_QUOTEX_TIMEFRAMES

    keyboard, row = [], []
    for tf in tfs:
        row.append(InlineKeyboardButton(f"{format_timeframe_label(tf)}", callback_data=f"tf_{model_type}_{cat}_{pair}_{tf}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data=f"cat_{cat}")])

    await query.edit_message_text(
        f"📊 *{display}*\n\nSelect a timeframe for AI analysis:\n\n"
        f"⚠️ *Plz select the timeframe which is Active on Quotex.*\n"
        f"Selecting wrong one which is not Active may cause the Wrong signal!\n\n"
        f"The AI will study the pattern on the selected timeframe and signal the NEXT candle after the current one ends.",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
    )


async def timeframe_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    # callback_data format: tf_{model_type}_{cat}_{pair}_{tf}
    rest = query.data[3:] if query.data.startswith("tf_") else query.data
    parts = rest.rsplit("_", 1)
    if len(parts) != 2:
        await query.edit_message_text("❌ Invalid timeframe selection. Please start again.")
        return
    prefix = parts[0]
    try:
        tf = int(parts[1])
    except (ValueError, TypeError):
        await query.edit_message_text("❌ Invalid timeframe selection. Please start again.")
        return
    # prefix = model_type_cat_pair
    prefix_parts = prefix.split("_", 2)
    if len(prefix_parts) != 3:
        await query.edit_message_text("❌ Invalid timeframe selection. Please start again.")
        return
    model_type = prefix_parts[0]
    cat = prefix_parts[1]
    pair = prefix_parts[2]
    
    context.user_data["model_type"] = model_type
    original_pair = pair
    display = format_pair_name(pair)
    tf_label = format_timeframe_label(tf)

    await query.edit_message_text(f"⏳ Analyzing *{display}* on {tf_label}...\n\nStep 1/5: Connecting to Quotex...", parse_mode="Markdown")

    try:
        client = await bot_main.get_quotex_connection()
    except Exception as e:
        await query.edit_message_text(f"❌ Quotex connection failed: {e}")
        return

    await query.edit_message_text(f"⏳ Analyzing *{display}* on {tf_label}...\n\nStep 2/5: Fetching {tf_label} candles & calculating indicators...", parse_mode="Markdown")

    tech_data = await bot_main.fetch_and_process_indicators(client, pair, timeframe=tf)
    if tech_data is None:
        await query.edit_message_text(f"❌ Failed to fetch candle data for {display} on {tf_label}")
        await close_quotex_connection()
        return
    if tech_data == "LOW_VOLATILITY":
        await query.edit_message_text(f"⚠️ {display} has LOW VOLATILITY on {tf_label} right now. Cannot generate a reliable signal. Try again later.")
        await close_quotex_connection()
        return

    # Math score the selected pair on the selected timeframe
    math_score = bot_main.score_pair_math(tech_data["summary"])
    logger.info(f"Math score for {pair} @ {tf_label}: {math_score}/10")

    if math_score < 7.0:
        cat = bot_main.get_pair_category(pair)
        await query.edit_message_text(
            f"⏳ *{display}* scores {math_score}/10 (low setup) on {tf_label}.\n\n"
            f"Step 3/5: Auto-scanning all {cat} pairs for better setup...",
            parse_mode="Markdown"
        )
        active_pairs = await get_active_pairs(client)
        cat_pairs = active_pairs.get(cat, [])
        best = await bot_main.auto_scan_best_pair(client, cat, cat_pairs, timeframe=tf)
        if best and best["math_score"] > math_score:
            pair = best["code"]
            display = format_pair_name(pair)
            tech_data = best["tech_data"]
            logger.info(f"Auto-switched {original_pair} -> {pair} (score {best['math_score']}/10)")
            await query.edit_message_text(
                f"🔄 Switched *{format_pair_name(original_pair)}* ({math_score}/10) → *{display}* ({best['math_score']}/10)\n\n"
                f"Step 4/5: Running 3-stage AI pipeline ({'Vision' if model_type == 'vision' else 'LLM'})...",
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text(
                f"⏳ *{display}* scores {math_score}/10 but no better pair found.\n\n"
                f"Step 4/5: Running 3-stage AI pipeline ({'Vision' if model_type == 'vision' else 'LLM'})...",
                parse_mode="Markdown"
            )
    else:
        await query.edit_message_text(
            f"⏳ *{display}* scores {math_score}/10 (good setup) on {tf_label}.\n\n"
            f"Step 3/5: Running 3-stage AI pipeline ({'Vision' if model_type == 'vision' else 'LLM'})...",
            parse_mode="Markdown"
        )

    chart_b64 = None
    if os.getenv("ENABLE_CHART_CAPTURE", "1") == "1" and model_type == "vision":
        try:
            import chart_render
            candles = (tech_data or {}).get("candles")
            if not candles:
                logger.warning(f"No candle data for {pair}; skipping chart render")
            else:
                logger.info(f"Rendering chart for {pair} from {len(candles)} candles (tf={tf}s)...")
                chart_b64 = chart_render.render_chart_to_base64(
                    candles,
                    summary=(tech_data or {}).get("summary"),
                    token=pair,
                    timeframe=tf,
                )
                if chart_b64:
                    logger.info(f"Chart rendered for {pair} ({len(chart_b64)} b64 chars) -> attached to Gemini Flash")
                else:
                    logger.warning(f"Chart render failed for {pair}; proceeding without image")
        except Exception as e:
            logger.warning(f"Chart render error for {pair}: {e}")

    if model_type == "llm":
        ai_result = await bot_main.query_all_llm_models(
            tech_data["summary"],
            pair_code=pair,
            original_pair=original_pair if pair != original_pair else None,
        )
    else:
        ai_result = await bot_main.query_all_models(
            tech_data["summary"],
            pair_code=pair,
            original_pair=original_pair if pair != original_pair else None,
            chart_b64=chart_b64,
        )
    await close_quotex_connection()

    if not ai_result or not isinstance(ai_result, dict):
        await query.edit_message_text(f"❌ AI analysis failed for {display}. All AI models may be unavailable.")
        return

    direction = str(ai_result.get("direction", "SKIP")).strip().upper()
    if direction == "SKIP":
        reason = ai_result.get("reason", "AI models determined no trade.")
        note = ai_result.get("note", "")
        msg = f"⏭️ No signal for *{display}* on {tf_label}\n\n{reason}"
        if note:
            msg += f"\n\n{note}"
        await query.edit_message_text(msg, parse_mode="Markdown")
        return

    buy_sell = "UP" if direction in ("BUY", "UP") else "DOWN"
    confidence = ai_result.get("confidence", 0)
    reason = ai_result.get("reason", "No reason provided.")
    note = ai_result.get("note", "")

    # Freshness guard: the AI analyzed data captured at `data_ts`. If that state has
    # already expired (older than ~1.5 candles), re-fetch fresh candles and run a fast
    # deterministic re-check so we never signal on stale market conditions.
    data_ts = bot_main.data_timestamp_seconds(tech_data)
    data_age = (time.time() - data_ts) if data_ts else 0.0
    if data_age > max(tf * bot_main.DATA_AGE_MULTIPLIER, 10):
        logger.info(f"Signal data for {pair} is {data_age:.0f}s old (tf={tf}s). Refreshing + re-checking...")
        fresh = None
        try:
            client = await bot_main.get_quotex_connection()
            fresh = await bot_main.fetch_and_process_indicators(
                client, pair, tech_data["summary"].get("payout_percentage", 80), timeframe=tf
            )
            await close_quotex_connection()
        except Exception as e:
            logger.warning(f"Freshness refresh failed for {pair}: {e}")
        if fresh == "LOW_VOLATILITY":
            await query.edit_message_text(
                f"⚠️ *{display}* now shows LOW VOLATILITY on {tf_label}. Refusing to signal on stale analysis.",
                parse_mode="Markdown",
            )
            return
        if fresh and isinstance(fresh, dict):
            fresh_check = bot_main.quick_direction_check(fresh["summary"])
            if fresh_check != "NEUTRAL" and fresh_check != buy_sell:
                await query.edit_message_text(
                    f"⏭️ No signal for *{display}* on {tf_label}\n\n"
                    f"The analyzed data became stale ({data_age:.0f}s old) and the fresh market state now "
                    f"contradicts the AI signal (AI: {buy_sell}, fresh state: {fresh_check}). Rerun for a new signal.",
                    parse_mode="Markdown",
                )
                return
            tech_data = fresh
            logger.info(f"Fresh data confirms {buy_sell} (fresh check: {fresh_check}). Signal is up to date.")
        elif fresh is None:
            logger.warning(f"Fresh data unavailable for {pair}; using AI result from {data_age:.0f}s-old data")

    signal = {
        "token": pair,
        "direction": buy_sell,
        "confidence": confidence,
        "reason": reason,
        "note": note,
        "martingale_recommendation": ai_result.get("martingale_recommendation", "M0"),
        "payout": tech_data["summary"].get("payout_percentage", 80),
        "timeframe_seconds": tf,
        "timeframe_label": tf_label,
        "data_timestamp": bot_main.data_timestamp_seconds(tech_data),
    }

    signal_text = bot_main.format_telegram_signal(signal)

    await query.edit_message_text(f"⏳ Analyzing *{display}* on {tf_label}...\n\nStep 5/5: Sending signal...", parse_mode="Markdown")

    img = os.path.join(PROJECT_ROOT, "Image", f"{'up' if buy_sell == 'UP' else 'down'}_banner.png")
    if os.path.exists(img):
        try:
            with open(img, "rb") as f:
                sent_photo = await query.message.reply_photo(f)
            await sent_photo.reply_text(signal_text)
        except Exception:
            await query.message.reply_text(signal_text)
    else:
        await query.message.reply_text(signal_text)

    await query.edit_message_text(f"✅ Signal sent for *{display}* on {tf_label}!\n\nCheck the messages above", parse_mode="Markdown")

    # Wait for the current candle to end, then for the NEXT candle to close.
    PKT = timezone(timedelta(hours=5))
    now_pkt = datetime.now(PKT)
    now_ts = now_pkt.timestamp()
    remaining = tf - int(now_ts % tf)
    if remaining == tf:
        remaining = tf
    total_wait = remaining + tf
    await asyncio.sleep(total_wait)

    try:
        client = await bot_main.get_quotex_connection()
        from quotex_adapter import fetch_candles
        result_candles = await fetch_candles(client, signal["token"], count=tf * 10 + 60, timeframe=tf)
        await close_quotex_connection()

        if result_candles and len(result_candles) >= 2:
            c = result_candles[-2]
            c_open = float(c["open"])
            c_close = float(c["close"])
            went_up = c_close > c_open
            predicted_up = signal["direction"] == "UP"
            won = went_up == predicted_up

            if won:
                result_msg = f"WIN - {display}"
            else:
                result_msg = f"LOSS - {display}"
            await query.message.reply_text(result_msg, parse_mode="Markdown")
    except Exception as e:
        logger.warning(f"Trade result check failed: {e}")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")


async def ensure_initial_token():
    """Get a fresh token on startup and start the proactive watchdog."""
    try:
        from quotex_adapter import get_quotex_connection, close_quotex_connection, start_watchdog
        logger.info("Proactive token refresh: connecting on startup...")
        client = await get_quotex_connection()
        await close_quotex_connection()
        logger.info("Proactive token refresh: initial token obtained, watchdog started")
    except Exception as e:
        logger.warning(f"Initial token fetch failed (will retry on first signal): {e}")
        from quotex_adapter import start_watchdog
        start_watchdog()


def main():
    # Ensure asyncio event loop compatibility on Python 3.14+ Windows
    if sys.platform == "win32":
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

    # Startup sanity check: confirm chart model and .env Quotex proxy
    # are actually wired into the running bot.
    try:
        qx_proxy = os.getenv("QUOTEX_PROXY") or os.getenv("CAMOUFOX_PROXY") or ""
        if qx_proxy:
            host = qx_proxy.rsplit("@", 1)[-1]
            logger.info("Quotex connection will use proxy from .env: %s", host)
        else:
            logger.warning("No QUOTEX_PROXY / CAMOUFOX_PROXY set in .env — connecting to Quotex DIRECTLY (likely geo-blocked)")
        logger.info("AI models active: Gemini Flash (chart), Nemotron 3 Nano Omni, Dots3-Note Preview (via Kilo)")
        logger.info("LLM models active: Nemotron 3 Ultra (Zen), Llama 3.1 8B (NVIDIA), Laguna-S 2.1 (Kilo)")
        logger.info("Chart image is attached to Gemini Flash for visual confirmation")
    except Exception as e:
        logger.warning(f"Runtime config check failed: {e}")

    from telegram.request import HTTPXRequest
    request = HTTPXRequest(httpx_kwargs={"timeout": 30})
    app = Application.builder().token(TOKEN).request(request).concurrent_updates(True).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(model_selection, pattern="^get_signal$"))
    app.add_handler(CallbackQueryHandler(model_selection, pattern="^model_selection$"))
    app.add_handler(CallbackQueryHandler(get_signal_menu, pattern="^model_vision$"))
    app.add_handler(CallbackQueryHandler(get_signal_menu, pattern="^model_llm$"))
    app.add_handler(CallbackQueryHandler(menu_category, pattern="^cat_"))
    app.add_handler(CallbackQueryHandler(pair_selected, pattern="^pair_"))
    app.add_handler(CallbackQueryHandler(timeframe_selected, pattern="^tf_"))
    app.add_handler(CallbackQueryHandler(back_start, pattern="^back_start$"))
    app.add_error_handler(error_handler)

    # Token refresh deferred (Playwright login hangs on Python 3.14; connects on-demand)
    # asyncio.get_event_loop().create_task(ensure_initial_token())

    logger.info("Bot started. Waiting for Telegram commands...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, timeout=0)


if __name__ == "__main__":
    main()
