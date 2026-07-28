"""Quick test for the updated quotex_adapter.py using pyquotex."""
import asyncio, logging
logging.basicConfig(level=logging.WARNING)

async def main():
    from quotex_adapter import get_quotex_connection, fetch_candles, get_active_pairs, get_asset_payout, close_quotex_connection
    from dotenv import load_dotenv
    load_dotenv()

    client = await get_quotex_connection()
    print(f"Connected: {type(client).__name__}")

    pairs = await get_active_pairs(client)
    print(f"OTC: {len(pairs['OTC'])}, REAL: {len(pairs['REAL'])}, CRYPTO: {len(pairs['CRYPTO'])}")

    if pairs['OTC']:
        print(f"Top OTC: {pairs['OTC'][0]}")

    asset = "EURUSD_otc"
    payout = await get_asset_payout(client, asset)
    print(f"{asset} payout: {payout}")

    candles = await fetch_candles(client, asset, count=3600, timeframe=60)
    print(f"Candles: {len(candles) if candles else 0}")

    if candles:
        print(f"First: O={candles[0]['open']} C={candles[0]['close']}")
        print(f"Last:  O={candles[-1]['open']} C={candles[-1]['close']}")

    await close_quotex_connection()
    print("Done")

asyncio.run(main())
