import asyncio, os, sys, json, logging
logging.basicConfig(level=logging.INFO)
sys.path.insert(0, r"C:\Users\PC\Desktop\Quotex Signal")
from dotenv import load_dotenv
load_dotenv(r"C:\Users\PC\Desktop\Quotex Signal\.env")
from quotex_adapter import _connect_with_token, load_session, close_quotex_connection

async def main():
    email = os.getenv("QUOTEX_EMAIL") or "slamismail8@gmail.com"
    session = load_session()
    token = session.get("token")
    print("email:", email, "| token:", (token or "")[:12] + "...", flush=True)

    client, err = await _connect_with_token(email, token, session)
    if client:
        bal = await client.get_balance()
        print("CONNECTED! balance:", bal, flush=True)
        await close_quotex_connection()
    else:
        print("FAILED:", err, flush=True)

asyncio.run(main())
