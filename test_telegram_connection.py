import os
import asyncio
from dotenv import load_dotenv
from telegram import Bot

async def main():
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    proxy_url = os.getenv("TELEGRAM_PROXY")
    base_url = os.getenv("TELEGRAM_BASE_URL")
    
    print("\n--- Testing Connection settings ---")
    print(f"Token: {token[:10]}...")
    print(f"Proxy URL: {proxy_url}")
    print(f"Base URL: {base_url}")
    
    # Configure bot instance
    from telegram.request import HTTPXRequest
    req_kwargs = {"httpx_kwargs": {"trust_env": False}}
    if proxy_url:
        req_kwargs["proxy"] = proxy_url
        req_kwargs["connect_timeout"] = 15.0
        req_kwargs["read_timeout"] = 15.0
        
    kwargs = {'request': HTTPXRequest(**req_kwargs)}
    if base_url:
        kwargs['base_url'] = base_url
        
    bot = Bot(token=token, **kwargs)
    
    try:
        print("Initializing bot...")
        await bot.initialize()
        print("Fetching bot info (getMe)...")
        me = await bot.get_me()
        print(f"Success! Bot username: @{me.username}")
    except Exception as e:
        print(f"Failed to connect to Telegram: {e}")
    finally:
        try:
            await bot.shutdown()
        except Exception:
            pass

if __name__ == "__main__":
    asyncio.run(main())
