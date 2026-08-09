"""Run the production Camoufox renewal locally with the IP proxy. Debug logging."""

import asyncio
import logging
import sys

sys.path.insert(0, r"C:\Users\PC\Desktop\Quotex Signal")

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

import renew_ssid


async def main():
    logging.info("Starting local Camoufox renewal test")
    token = await renew_ssid._camoufox_login()
    logging.info("TOKEN_RESULT: %s", token)


if __name__ == "__main__":
    asyncio.run(main())
