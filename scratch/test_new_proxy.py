import httpx, warnings, asyncio
warnings.filterwarnings('ignore')

PROXY = 'http://DVSb5shsyy:2EjNlGB@104.219.238.234:38457'

def test_http():
    with httpx.Client(proxy=PROXY, timeout=25, verify=False, follow_redirects=True) as c:
        ip = c.get('https://api.ipify.org').text.strip()
        r = c.get('https://market-qx.trade/en/sign-in/')
        t = r.text
        geo = 'not available in your region' in t or 'your region' in t
        form = 'name="email"' in t
        cf = 'Just a moment' in t
        return ip, geo, form, cf, len(t)

async def test_ws():
    import websockets
    try:
        async with websockets.connect(
            'wss://ws2.qxbroker.com/socket.io/?EIO=3&transport=websocket',
            proxy=PROXY, open_timeout=25,
        ) as ws:
            return True
    except Exception as e:
        return f'FAIL: {type(e).__name__} {str(e)[:120]}'

ip, geo, form, cf, ln = test_http()
print(f'HTTP IP: {ip}')
print(f'GEO-BLOCKED: {geo} | FORM OK: {form} | CLOUDFLARE: {cf} | len={ln}')
print(f'WS: {asyncio.run(test_ws())}')
