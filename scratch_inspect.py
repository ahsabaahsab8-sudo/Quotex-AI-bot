import asyncio
import httpx
from bs4 import BeautifulSoup

async def test_host(host):
    print(f"\n--- Testing host: {host} ---")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
            r1 = await client.get(f"https://{host}/en")
            print(f"GET /en: {r1.status_code} -> {r1.url}")
            
            r2 = await client.get(f"https://{host}/en/sign-in/modal/", cookies=r1.cookies)
            print(f"GET modal: {r2.status_code}, Length: {len(r2.text)}")
            
            soup = BeautifulSoup(r2.text, 'html.parser')
            forms = soup.find_all('form')
            print(f"Found {len(forms)} form(s)")
            for i, form in enumerate(forms):
                print(f"Form {i}: action='{form.get('action')}', method='{form.get('method')}'")
                inputs = form.find_all('input')
                input_names = [inp.get('name') for inp in inputs]
                print(f"  Inputs: {input_names}")
                token = form.find("input", {"name": "_token"})
                if token:
                    print(f"  _token value: {token.get('value')}")
    except Exception as e:
        print(f"Failed for host {host}: {e}")

async def main():
    hosts = [
        "qxbroker.io",
        "qxbroker.pro",
        "quotex.market",
        "quotex-market.com",
        "quotex-market.io",
        "quotex-market.pro",
        "qx-market.com",
        "qx-market.io",
        "market-qx.trade",
        "qxbroker.com",
        "quotex.io",
        "quotex.com"
    ]
    for host in hosts:
        await test_host(host)

if __name__ == "__main__":
    asyncio.run(main())
