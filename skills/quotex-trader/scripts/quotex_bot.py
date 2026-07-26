import os
import sys
import asyncio
import json
import time
import logging
from datetime import datetime, timezone, timedelta

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv()

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

import main as bot_main

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN not set")
    sys.exit(1)


async def get_active_pairs(client) -> dict:
    instruments = await client.get_instruments()
    otc, real, crypto = [], [], []
    for inst in instruments:
        code = inst[1]
        category = inst[3]
        is_open = inst[14]
        payout = inst[5]
        
        is_otc = "_otc" in code.lower()
        if is_otc:
            # Show all active OTC currencies and assets (no is_open/payout restriction)
            if category == "currency":
                otc.append((payout, code))
            elif category in ("crypto", "cryptocurrency", "commodity", "index"):
                crypto.append((payout, code))
        else:
            if not is_open or payout < 70:
                continue
            if category == "currency":
                real.append((payout, code))
            elif category in ("crypto", "cryptocurrency", "commodity", "index"):
                crypto.append((payout, code))
                
    sort_key = lambda x: (-x[0], x[1])
    return {"OTC": sorted(otc, key=sort_key), "REAL": sorted(real, key=sort_key), "CRYPTO": sorted(crypto, key=sort_key)}



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
        await client.close()
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
    original_pair = pair
    display = format_pair_name(pair)

    await query.edit_message_text(f"⏳ Analyzing *{display}*...\n\nStep 1/5: Connecting to Quotex...", parse_mode="Markdown")

    try:
        client = await bot_main.get_quotex_connection()
    except Exception as e:
        await query.edit_message_text(f"❌ Quotex connection failed: {e}")
        return

    await query.edit_message_text(f"⏳ Analyzing *{display}*...\n\nStep 2/5: Fetching candles & calculating indicators...", parse_mode="Markdown")

    tech_data = await bot_main.fetch_and_process_indicators(client, pair)
    if tech_data is None:
        await query.edit_message_text(f"❌ Failed to fetch candle data for {display}")
        await client.close()
        return
    if tech_data == "LOW_VOLATILITY":
        await query.edit_message_text(f"⚠️ {display} has LOW VOLATILITY right now. Cannot generate a reliable signal. Try again later.")
        await client.close()
        return

    # Math score the selected pair
    math_score = bot_main.score_pair_math(tech_data["summary"])
    logger.info(f"Math score for {pair}: {math_score}/10")

    if math_score < 7.0:
        cat = bot_main.get_pair_category(pair)
        await query.edit_message_text(
            f"⏳ *{display}* scores {math_score}/10 (low setup).\n\n"
            f"Step 3/5: Auto-scanning all {cat} pairs for better setup...",
            parse_mode="Markdown"
        )
        active_pairs = await get_active_pairs(client)
        cat_pairs = active_pairs.get(cat, [])
        best = await bot_main.auto_scan_best_pair(client, cat, cat_pairs)
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
            f"⏳ *{display}* scores {math_score}/10 (good setup).\n\n"
            f"Step 3/5: Running 3-stage AI pipeline...",
            parse_mode="Markdown"
        )

    ai_result = await bot_main.query_all_models(tech_data["summary"], pair_code=pair, original_pair=original_pair if pair != original_pair else None)
    await client.close()

    if not ai_result or not isinstance(ai_result, dict):
        await query.edit_message_text(f"❌ AI analysis failed for {display}. All AI models may be unavailable.")
        return

    direction = str(ai_result.get("direction", "SKIP")).strip().upper()
    if direction == "SKIP":
        reason = ai_result.get("reason", "AI models determined no trade.")
        note = ai_result.get("note", "")
        msg = f"⏭️ No signal for *{display}*\n\n{reason}"
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
    }

    signal_text = bot_main.format_telegram_signal(signal)

    await query.edit_message_text(f"⏳ Analyzing *{display}*...\n\nStep 5/5: Sending signal...", parse_mode="Markdown")

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

    await query.edit_message_text(f"✅ Signal sent for *{display}*!\n\n👉 Check the messages above 👆", parse_mode="Markdown")

    PKT = timezone(timedelta(hours=5))
    now_pkt = datetime.now(PKT)
    remaining = 60 - now_pkt.second
    total_wait = remaining + 60
    await asyncio.sleep(total_wait)

    try:
        client = await bot_main.get_quotex_connection()
        candles_data = await client.get_historical_candles(signal["token"], 180, 60)
        await client.close()

        if candles_data and len(candles_data) >= 2:
            c = candles_data[-2] if isinstance(candles_data[-2], list) else (candles_data[-2] if isinstance(candles_data[-2], dict) else None)
            if c:
                c_open = float(c[1]) if isinstance(c, list) else float(c["open"])
                c_close = float(c[2]) if isinstance(c, list) else float(c["close"])
                went_up = c_close > c_open
                predicted_up = signal["direction"] == "UP"
                won = went_up == predicted_up

                if won:
                    result_msg = f"✅ *Trade WIN* - *{display}*\n\nTrade won sureshot"
                else:
                    result_msg = f"❌ *Trade LOSS* - *{display}*\n\nAI already showed why this can loss. You can check the reason. Do not worry. Try for another one."
                await query.message.reply_text(result_msg, parse_mode="Markdown")
    except Exception as e:
        logger.warning(f"Trade result check failed: {e}")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")


def main():
    from telegram.request import HTTPXRequest
    request = HTTPXRequest(httpx_kwargs={"trust_env": False})
    app = Application.builder().token(TOKEN).request(request).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(get_signal_menu, pattern="^get_signal$"))
    app.add_handler(CallbackQueryHandler(menu_category, pattern="^cat_"))
    app.add_handler(CallbackQueryHandler(pair_selected, pattern="^pair_"))
    app.add_handler(CallbackQueryHandler(back_start, pattern="^back_start$"))
    app.add_error_handler(error_handler)
    logger.info("Bot started. Waiting for Telegram commands...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
