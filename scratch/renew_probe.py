"""Live renew_ssid._camoufox_login() test with the NEW proxy, text-visible."""
import asyncio, os, sys, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)],
)

import renew_ssid as r


async def main():
    print(f'=== CAMOUFOX_PROXY = {os.getenv("CAMOUFOX_PROXY")}', flush=True)
    print('=== Starting _camoufox_login() with new proxy ...', flush=True)
    try:
        token = await asyncio.wait_for(r._camoufox_login(), timeout=280)
        print(f'=== DONE. TOKEN = {(token[:12] + "..." + token[-4:]) if token else None}', flush=True)
    except asyncio.TimeoutError:
        print('=== TIMED OUT after 280s', flush=True)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print('=== ERR:', type(e).__name__, str(e)[:300], flush=True)


asyncio.run(main())
