import os
import sys
import asyncio
from unittest.mock import AsyncMock, MagicMock

# Add project root and scripts folder to python path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "skills", "quotex-trader", "scripts"))

# Mock environment variable for telegram token
os.environ["TELEGRAM_BOT_TOKEN"] = "123456:mock_token"

import quotex_bot

async def test_get_active_pairs():
    print("Running test_get_active_pairs...")
    client = MagicMock()
    # Mock return value of client.get_instruments()
    # Format of each instrument inst:
    # inst[1] = code, inst[2] = display_name, inst[3] = category, inst[5] = payout, inst[14] = is_open
    mock_instruments = [
        # OTC Currencies (some marked Open: False or Payout < 70, but we want ALL of them for OTC)
        [0, "EURUSD_otc", "EUR/USD (OTC)", "currency", 0, 93, 0, 0, 0, 0, 0, 0, [], 0, False],
        [0, "GBPUSD_otc", "GBP/USD (OTC)", "currency", 0, 65, 0, 0, 0, 0, 0, 0, [], 0, False],
        [0, "USDJPY_otc", "USD/JPY (OTC)", "currency", 0, 90, 0, 0, 0, 0, 0, 0, [], 0, True],
        
        # Real Market Currencies (should be filtered if not open or payout < 70)
        [0, "EURUSD", "EUR/USD", "currency", 0, 80, 0, 0, 0, 0, 0, 0, [], 0, True],
        [0, "GBPUSD", "GBP/USD", "currency", 0, 65, 0, 0, 0, 0, 0, 0, [], 0, True],  # Payout < 70
        [0, "USDJPY", "USD/JPY", "currency", 0, 90, 0, 0, 0, 0, 0, 0, [], 0, False], # Open: False
        
        # Crypto
        [0, "BTCUSD_otc", "Bitcoin (OTC)", "cryptocurrency", 0, 92, 0, 0, 0, 0, 0, 0, [], 0, True],
        [0, "ETHUSD", "Ethereum", "cryptocurrency", 0, 75, 0, 0, 0, 0, 0, 0, [], 0, True],
    ]
    client.get_instruments = AsyncMock(return_value=mock_instruments)
    
    pairs = await quotex_bot.get_active_pairs(client)
    
    print(f"OTC pairs: {pairs['OTC']}")
    print(f"REAL pairs: {pairs['REAL']}")
    print(f"CRYPTO pairs: {pairs['CRYPTO']}")
    
    # OTC currencies should include EURUSD_otc (payout 93%), GBPUSD_otc (payout 65%), USDJPY_otc (payout 90%)
    # Even if they are Open: False or Payout < 70, we fetch ALL OTC currencies.
    assert len(pairs["OTC"]) == 3, f"Expected 3 OTC pairs, got {len(pairs['OTC'])}"
    assert pairs["OTC"][0] == (93, "EURUSD_otc")
    assert pairs["OTC"][1] == (90, "USDJPY_otc")
    assert pairs["OTC"][2] == (65, "GBPUSD_otc")
    
    # REAL market currencies should filter out GBPUSD (payout < 70) and USDJPY (open: False).
    # Only EURUSD should remain.
    assert len(pairs["REAL"]) == 1, f"Expected 1 REAL pair, got {len(pairs['REAL'])}"
    assert pairs["REAL"][0] == (80, "EURUSD")
    
    # CRYPTO list should contain both BTCUSD_otc (OTC, so kept) and ETHUSD (Open: True, payout 75 >= 70).
    assert len(pairs["CRYPTO"]) == 2, f"Expected 2 CRYPTO pairs, got {len(pairs['CRYPTO'])}"
    
    print("PASS: test_get_active_pairs")

def test_format_pair_button_label():
    print("Running test_format_pair_button_label...")
    
    # OTC
    label_otc = quotex_bot.format_pair_button_label("EURUSD_otc", 93)
    assert label_otc == "EUR/USD (OTC) (93%)", f"Expected 'EUR/USD (OTC) (93%)', got '{label_otc}'"
    
    # Real
    label_real = quotex_bot.format_pair_button_label("EURUSD", 82)
    assert label_real == "EUR/USD (82%)", f"Expected 'EUR/USD (82%)', got '{label_real}'"
    
    print("PASS: test_format_pair_button_label")

async def test_start_handler():
    print("Running test_start_handler...")
    
    update = MagicMock()
    update.message = AsyncMock()
    update.edit_message_text = AsyncMock()
    update.callback_query = None
    context = MagicMock()
    
    await quotex_bot.start(update, context)
    
    # Verify reply_text was called with GET SIGNAL button
    args, kwargs = update.message.reply_text.call_args
    assert "Welcome to the Quotex Real Market AI" in args[0]
    keyboard = kwargs["reply_markup"].inline_keyboard
    assert len(keyboard) == 1
    assert keyboard[0][0].text == "🔥 GET SIGNAL"
    assert keyboard[0][0].callback_data == "get_signal"
    
    print("PASS: test_start_handler")

async def test_get_signal_menu():
    print("Running test_get_signal_menu...")
    
    update = MagicMock()
    update.callback_query = MagicMock()
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    context = MagicMock()
    
    await quotex_bot.get_signal_menu(update, context)
    
    # Verify callback query was answered and message was edited
    update.callback_query.answer.assert_called_once()
    args, kwargs = update.callback_query.edit_message_text.call_args
    assert "Choose a category to select a pair" in args[0]
    keyboard = kwargs["reply_markup"].inline_keyboard
    
    # E.g., OTC, REAL, CRYPTO, Back button
    assert len(keyboard) == 4
    assert keyboard[0][0].text == "💱 OTC Currencies"
    assert keyboard[0][0].callback_data == "cat_OTC"
    assert keyboard[3][0].text == "🔙 Back"
    assert keyboard[3][0].callback_data == "back_start"
    
    print("PASS: test_get_signal_menu")

async def run_all():
    await test_get_active_pairs()
    test_format_pair_button_label()
    await test_start_handler()
    await test_get_signal_menu()
    print("ALL TESTS PASSED!")

if __name__ == "__main__":
    asyncio.run(run_all())
