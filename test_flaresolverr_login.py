"""Test FlareSolverr to bypass Cloudflare and get real session cookie from quotex."""
import requests, json, os, re
from dotenv import load_dotenv
from bs4 import BeautifulSoup

load_dotenv()

email = os.getenv("QUOTEX_EMAIL")
password = os.getenv("QUOTEX_PASSWORD")

FS_URL = "http://localhost:8191/v1"
BASE = "https://market-quotex.pro"

def fs_request(cmd, **kwargs):
    payload = {"cmd": cmd}
    payload.update(kwargs)
    return requests.post(FS_URL, json=payload, timeout=120).json()

# Step 1: Create a session in flaresolverr
print("Creating FlareSolverr session...")
session_resp = fs_request("sessions.create")
session_id = session_resp.get("session", "")
print(f"Session ID: {session_id}")

# Step 2: GET the login page via FlareSolverr
print(f"\nGET {BASE}/en/sign-in/ via FlareSolverr...")
resp = fs_request("request.get",
    url=f"{BASE}/en/sign-in/",
    session=session_id,
    maxTimeout=60000)
solution = resp.get("solution", {})
status = solution.get("status", 0)
print(f"Status: {status}")
print(f"Cookies: {solution.get('cookies', [])}")

if status == 200:
    html = solution.get("response", "")
    soup = BeautifulSoup(html, "html.parser")
    csrf_input = soup.select_one('#tab-1 input[name="_token"]')
    if not csrf_input:
        csrf_input = soup.select_one('input[name="_token"]')
    if csrf_input:
        csrf = csrf_input.get("value")
        print(f"CSRF token: {csrf[:30]}...")

        # Step 3: POST login form via FlareSolverr
        print(f"\nPOST {BASE}/en/sign-in/ via FlareSolverr...")
        resp2 = fs_request("request.post",
            url=f"{BASE}/en/sign-in/",
            session=session_id,
            postData=f"_token={csrf}&email={email}&password={password}&remember=1",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            maxTimeout=60000)
        sol2 = resp2.get("solution", {})
        status2 = sol2.get("status", 0)
        print(f"POST Status: {status2}")
        print(f"Response cookies: {sol2.get('cookies', [])}")
        print(f"Response headers: {sol2.get('headers', {})}")
        
        # Check all cookies from session
        print(f"\nNavigating to trade page...")
        resp3 = fs_request("request.get",
            url=f"{BASE}/en/trade",
            session=session_id,
            maxTimeout=60000)
        sol3 = resp3.get("solution", {})
        
        cookies = sol3.get("cookies", [])
        print(f"\nAll cookies:")
        for c in cookies:
            print(f"  {c.get('name')} = {c.get('value')[:50] if c.get('value') else 'None'}")
            if c.get('name', '').lower() in ('session', 'ssid', 'qx_session'):
                print(f"  *** SESSION COOKIE: {c['value']} ***")
        
        html3 = sol3.get("response", "")
        match = re.search(r'window\.settings\s*=\s*(\{.*?\});', html3, re.S)
        if match:
            try:
                settings = json.loads(match.group(1))
                token = settings.get('token')
                print(f"\nwindow.settings.token: {token[:50] if token else 'N/A'}...")
            except:
                print("Could not parse window.settings")
    else:
        print("No CSRF token found")
        # Print form info
        forms = soup.find_all('form')
        print(f"Forms: {len(forms)}")
        for f in forms:
            print(f"  action={f.get('action')}")
else:
    print(f"Failed to get login page: {solution.get('response', '')[:500]}")
