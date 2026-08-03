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
    get_asset_timeframes as adapter_get_asset_timeframes,
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


async def get_signal_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [[InlineKeyboardButton(f"{CATEGORY_EMOJI[c]} {CATEGORY_LABEL[c]}", callback_data=f"cat_{c}")] for c in CATEGORY_LABEL]
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="back_start")])
    
    await query.edit_message_text(
        "Choose a category to select a pair for AI analysis:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def menu_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cat = query.data.replace("cat_", "")
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
        row.append(InlineKeyboardButton(label, callback_data=f"pair_{code}"))
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
    await start(query, context)


async def pair_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    pair = query.data.replace("pair_", "")
    display = format_pair_name(pair)

    await query.edit_message_text(f"⏳ Checking active timeframes for *{display}*...", parse_mode="Markdown")

    try:
        client = await bot_main.get_quotex_connection()
        tfs = await adapter_get_asset_timeframes(client, pair)
        await close_quotex_connection()
    except Exception as e:
        await query.edit_message_text(f"❌ Failed to connect to Quotex: {e}")
        return

    if not tfs:
        await query.edit_message_text(f"❌ No active timeframes found for {display}")
        return

    keyboard, row = [], []
    for tf in tfs:
        row.append(InlineKeyboardButton(f"{format_timeframe_label(tf)}", callback_data=f"tf_{pair}_{tf}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="get_signal")])

    await query.edit_message_text(
        f"📊 *{display}*\n\nSelect a timeframe for AI analysis:\n\n"
        f"The AI will study the pattern on the selected timeframe and signal the NEXT candle after the current one ends.",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
    )


async def timeframe_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_", 2)
    if len(parts) != 3:
        await query.edit_message_text("❌ Invalid timeframe selection. Please start again.")
        return
    pair = parts[1]
    tf = int(parts[2])
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
                f"Step 4/5: Running 3-stage AI pipeline...",
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text(
                f"⏳ *{display}* scores {math_score}/10 but no better pair found.\n\n"
                f"Step 4/5: Running 3-stage AI pipeline...",
                parse_mode="Markdown"
            )
    else:
        await query.edit_message_text(
            f"⏳ *{display}* scores {math_score}/10 (good setup) on {tf_label}.\n\n"
            f"Step 3/5: Running 3-stage AI pipeline...",
            parse_mode="Markdown"
        )

    ai_result = await bot_main.query_all_models(tech_data["summary"], pair_code=pair, original_pair=original_pair if pair != original_pair else None)
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
    from telegram.request import HTTPXRequest
    proxy_url = os.getenv("TELEGRAM_PROXY")
    req_kwargs = {"httpx_kwargs": {"timeout": 30}}
    if proxy_url:
        logger.info(f"Using proxy: {proxy_url}")
        req_kwargs["proxy"] = proxy_url
        req_kwargs["connect_timeout"] = 15.0
        req_kwargs["read_timeout"] = 15.0
    request = HTTPXRequest(**req_kwargs)
    app = Application.builder().token(TOKEN).request(request).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(get_signal_menu, pattern="^get_signal$"))
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
