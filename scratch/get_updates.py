import os
import asyncio
import httpx
from dotenv import load_dotenv

async def main():
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        print("Status code:", response.status_code)
        print("JSON response:")
        print(response.json())

if __name__ == "__main__":
    asyncio.run(main())
