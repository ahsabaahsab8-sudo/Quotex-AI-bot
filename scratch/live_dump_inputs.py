"""LIVE diagnostic: fill login, submit, then dump ALL inputs as they appear
to find the actual OTP field name. Browser stays open so user can watch.
"""
import asyncio, os, logging
from datetime import datetime, timezone, timedelta
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
from dotenv import load_dotenv
load_dotenv()

PROXY = {'server': 'http://104.219.238.233:32771', 'username': 'DVSmpzf89o', 'password': 'It6t7Ev'}
EMAIL = os.getenv('QUOTEX_EMAIL')
PASSWORD = os.getenv('QUOTEX_PASSWORD')
login_ts = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=10)


async def dump_inputs(page, tag):
    info = await page.evaluate("""() => {
        var out = [];
        document.querySelectorAll('input').forEach(function(i){
            var r = i.getBoundingClientRect();
            out.push({name: i.name, type: i.type, ph: (i.placeholder||'').slice(0,30),
                      visible: r.width > 0 && r.height > 0, cls: (i.className||'').slice(0,40)});
        });
        return out;
    }""")
    print(f'>>> INPUTS[{tag}]: {info}')
    btns = await page.evaluate("""() => {
        var out = [];
        document.querySelectorAll('button').forEach(function(b){
            var r = b.getBoundingClientRect();
            out.push({text: (b.textContent||'').trim().slice(0,25), type: b.type,
                      visible: r.width > 0 && r.height > 0});
        });
        return out;
    }""")
    print(f'>>> BUTTONS[{tag}]: {btns}')
    return info, btns


async def main():
    from camoufox.async_api import AsyncCamoufox
    async with AsyncCamoufox(
        humanize=True, geoip=False, disable_coop=True, headless=False,
        proxy=PROXY, persistent_context=True,
        user_data_dir='sessions/camoufox_chart_profile',
        i_know_what_im_doing=True, window=(1366, 860),
    ) as context:
        page = await context.new_page()

        print('>>> Opening sign-in page ...')
        await page.goto('https://market-qx.trade/en/sign-in/', wait_until='domcontentloaded', timeout=120000)
        title = await page.title()
        print('>>> Title:', title)
        if 'Just a moment' in title:
            print('>>> Cloudflare detected...')
            try:
                await page.wait_for_function("() => !document.title.includes('Just a moment')", timeout=120000)
            except Exception:
                pass
        await asyncio.sleep(5)

        print('>>> Filling email + password ...')
        r = await page.evaluate("""(args) => {
            var emails = document.querySelectorAll('input[name="email"]');
            var passes = document.querySelectorAll('input[name="password"]');
            if (!emails.length || !passes.length) return "no inputs found";
            var email = emails.length > 1 ? emails[1] : emails[0];
            var pass = passes.length > 1 ? passes[1] : passes[0];
            email.value = args[0];
            pass.value = args[1];
            email.dispatchEvent(new Event('input', { bubbles: true }));
            pass.dispatchEvent(new Event('input', { bubbles: true }));
            return "filled";
        }""", [EMAIL, PASSWORD])
        print('>>> fill:', r)
        await asyncio.sleep(2)
        await dump_inputs(page, 'after-fill')

        print('>>> Submitting via form submit (QXvId flow)...')
        sub = await page.evaluate("""() => {
            var form = document.querySelector('#tab-1 form[action*="/sign-in"]');
            if (!form) return "no form";
            try {
                form.requestSubmit();
                return "requestSubmit called";
            } catch(e) {
                var btn = Array.from(form.querySelectorAll('button')).find(
                    b => b.textContent.trim() === 'Sign in');
                if (btn) { btn.click(); return "clicked sign in"; }
                form.submit();
                return "form.submit called";
            }
        }""")
        print('>>> submit:', sub)

        for i in range(40):
            await asyncio.sleep(3)
            url = page.url
            print(f'>>> [{i*3+3}s] url={url}')
            if 'sign-in' not in url.lower():
                print('>>> NAVIGATED to:', url)
                break
            info, btns = await dump_inputs(page, f'step{i}')
            # detect any otp-ish field
            otpish = [x for x in info if any(k in (x['name'] + x['ph']).lower()
                                             for k in ['code', 'otp', 'pin', '2fa', 'verif', 'token'])]
            if otpish:
                print('>>> OTP-LIKE FIELD:', otpish)

        print('>>> Keeping browser open 60s for you to inspect...')
        await asyncio.sleep(60)


asyncio.run(main())
