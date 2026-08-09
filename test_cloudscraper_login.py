"""Test cloudscraper login to get real session cookie (not guest token)."""
import cloudscraper
from bs4 import BeautifulSoup
import json, os
from dotenv import load_dotenv

load_dotenv()

email = os.getenv("QUOTEX_EMAIL")
password = os.getenv("QUOTEX_PASSWORD")

# Try both domains
for base_url in ["https://market-quotex.pro", "https://qxbroker.com"]:
    print(f"\n=== Trying {base_url} ===")
    scraper = cloudscraper.create_scraper()
    
    # Step 1: GET login page → extract CSRF
    login_url = f"{base_url}/en/sign-in/"
    print(f"GET {login_url}")
    try:
        resp = scraper.get(login_url, timeout=30)
        print(f"Status: {resp.status_code}")
        
        soup = BeautifulSoup(resp.text, "html.parser")
        csrf_input = soup.select_one('#tab-1 input[name="_token"]')
        if csrf_input:
            csrf = csrf_input.get("value")
            print(f"CSRF token: {csrf[:30]}...")
        else:
            # Try alternative selectors
            csrf_input = soup.select_one('input[name="_token"]')
            if csrf_input:
                csrf = csrf_input.get("value")
                print(f"CSRF token (alt): {csrf[:30]}...")
            else:
                print("No CSRF token found in page")
                # Check if there's a different form structure
                forms = soup.find_all('form')
                print(f"Forms found: {len(forms)}")
                for i, form in enumerate(forms):
                    action = form.get('action', '')
                    print(f"  Form {i}: action={action}")
                continue
        
        # Step 2: POST login form with CSRF
        post_url = f"{base_url}/en/sign-in/"
        print(f"POST {post_url}")
        resp2 = scraper.post(post_url,
            data={"_token": csrf, "email": email, "password": password, "remember": "1"},
            allow_redirects=False,
            timeout=30)
        print(f"POST status: {resp2.status_code}")
        print(f"Location: {resp2.headers.get('Location', 'none')}")
        print(f"Cookies: {dict(scraper.cookies)}")
        
        # Check for session cookie
        cookies_dict = dict(scraper.cookies)
        session_cookie = None
        for k, v in cookies_dict.items():
            if k.lower() in ("session", "ssid", "qx_session"):
                session_cookie = v
                print(f"\n*** REAL SESSION COOKIE FOUND: {k} = {v} ***")
        
        if session_cookie:
            print(f"\nSUCCESS! Real session token: {session_cookie[:30]}...")
            
            # Step 3: Get trading page to extract window.settings.token
            target = f"{base_url}/en/trade"
            resp3 = scraper.get(target, timeout=30)
            if resp3.status_code == 200:
                import re
                match = re.search(r'window\.settings\s*=\s*(\{.*?\});', resp3.text, re.S)
                if match:
                    try:
                        settings = json.loads(match.group(1))
                        token = settings.get('token')
                        print(f"window.settings.token: {token[:30] if token else 'N/A'}...")
                    except:
                        print("Could not parse window.settings")
            
            # Build the full SSID frame
            ssid = f'42["authorization",{{"session":"{session_cookie}","isDemo":0,"tournamentId":0}}]'
            print(f"\nFull SSID: {ssid[:60]}...")
            print(f"\n✅ REAL SESSION TOKEN obtained from {base_url}")
            break
        else:
            print("No session cookie found")
            # Try following redirect
            if resp2.status_code in (301, 302, 303, 307):
                loc = resp2.headers.get("Location")
                if loc:
                    if not loc.startswith("http"):
                        loc = base_url + loc
                    print(f"Following redirect to {loc}")
                    resp3 = scraper.get(loc, timeout=30)
                    print(f"Redirect GET status: {resp3.status_code}")
                    print(f"Cookies after redirect: {dict(scraper.cookies)}")
                    
    except Exception as e:
        print(f"Error: {e}")
