import httpx, warnings
warnings.filterwarnings('ignore')
proxy = 'http://DVSmpzf89o:It6t7Ev@104.219.238.233:32771'
ok = geo = err = 0
for i in range(8):
    try:
        with httpx.Client(proxy=proxy, timeout=25, verify=False, follow_redirects=True) as c:
            r = c.get('https://market-qx.trade/en/sign-in/')
            t = r.text
            ip = c.get('https://api.ipify.org').text.strip()
        if 'not available in your region' in t or 'your region' in t:
            geo += 1; print(f'{i}: GEO-BLOCK ip={ip}')
        elif 'Sign In To Your Account' in t or 'name="email"' in t:
            ok += 1; print(f'{i}: FORM OK ip={ip}')
        else:
            err += 1; print(f'{i}: UNKNOWN ip={ip} len={len(t)}')
    except Exception as e:
        err += 1; print(f'{i}: FAIL {type(e).__name__}')
print(f'--- ok={ok} geo={geo} err={err}')
