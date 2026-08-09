import asyncio
from pyppeteer import connect

async def main():
    browser = await connect(browserURL='http://127.0.0.1:9222', defaultViewport={'width':900,'height':700})
    page = await browser.newPage()
    cookies = [{'name': 'ssid', 'value': 'ejpGXpuGocySKYsiPvwa7m8XtX2bufEPjX2wTcog', 'url': 'https://market-qx.trade'}]
    await page.setCookie(*cookies)
    try:
        await page.goto('https://market-qx.trade/en/trade?asset=EURUSD_otc', {'waitUntil':'domcontentloaded', 'timeout':40000})
    except Exception as e:
        print('GOTO ERR:', e)
    await asyncio.sleep(15)
    print('URL:', page.url)
    try:
        print('TITLE:', await page.title())
    except Exception as e:
        print('TITLE ERR:', e)
    content = await page.content()
    print('LEN:', len(content))
    print('HAS cloudflare:', 'Just a moment' in content or 'cf-challenge' in content.lower())
    print('HAS sign-in:', 'sign-in' in page.url.lower())
    print('HAS trade:', '/trade' in page.url.lower())
    await page.screenshot({'path': r'C:\Users\PC\Desktop\Quotex Signal\scratch\pyppeteer_qx.png'})
    await browser.close()

asyncio.run(main())
