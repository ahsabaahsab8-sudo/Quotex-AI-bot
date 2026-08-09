import httpx, warnings
warnings.filterwarnings('ignore')
proxy = 'http://DVSmpzf89o:It6t7Ev@104.219.238.233:32771'
with httpx.Client(proxy=proxy, timeout=25, verify=False, follow_redirects=True) as c:
    r = c.get('https://market-qx.trade/en/sign-in/')
    t = r.text
    print('LEN:', len(t))
    print('HEAD 300:', t[:300].replace('\n', ' '))
    print('TITLE?', 'Just a moment' in t, '| region msg?', 'your region' in t, '| email?', 'name="email"' in t)
    print('has cf-challenge:', 'challenge-platform' in t or 'cf-chl' in t or 'cf_chl' in t)
