"""Test uc login with direct email tab navigation."""
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
import json, os, time
from dotenv import load_dotenv

load_dotenv()
email = os.getenv("QUOTEX_EMAIL")
password = os.getenv("QUOTEX_PASSWORD")

options = uc.ChromeOptions()
# Block Google OAuth redirect
prefs = {"profile.default_content_setting_values.notifications": 2}
options.add_experimental_option("prefs", prefs)

driver = uc.Chrome(version_main=150, headless=False, options=options)
wait = WebDriverWait(driver, 30)

try:
    # Try navigating to the trade page directly first (will redirect to login)
    print("Navigating to trade page...")
    driver.get("https://market-quotex.pro/en/trade")
    time.sleep(5)
    print(f"URL after trade: {driver.current_url}")
    
    # Check if we're on login page
    if "sign-in" in driver.current_url or "accounts.google" in driver.current_url:
        print("Redirected to login")
        
        # If redirected to Google, go back to sign-in form
        if "accounts.google" in driver.current_url:
            driver.get("https://market-quotex.pro/en/sign-in/")
            time.sleep(5)
            print(f"URL after sign-in: {driver.current_url}")
        
        # Try clicking email tab if redirected to social
        if "accounts.google" in driver.current_url:
            print("Still at Google - trying direct sign-in URL with email tab")
            driver.get("https://market-quotex.pro/en/sign-in/#tab-1")
            time.sleep(3)
            print(f"URL now: {driver.current_url}")
        
        # Check if there's a social login that we need to skip
        page_source = driver.page_source
        
        # Try finding email/password form
        try:
            email_input = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="email"], input[name="email"]'))
            )
            print("Email input found!")
            
            # Find password
            pwd_input = driver.find_element(By.CSS_SELECTOR, 'input[type="password"], input[name="password"]')
            
            email_input.clear()
            email_input.send_keys(email)
            pwd_input.clear()
            pwd_input.send_keys(password)
            pwd_input.send_keys(Keys.RETURN)
            
            time.sleep(8)
            print(f"After login URL: {driver.current_url}")
            
        except Exception as e:
            print(f"Could not find email form: {e}")
            # Print page structure
            print(f"Page URL: {driver.current_url}")
            with open("debug_login_page.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            print("Saved page source to debug_login_page.html")
    
    # Get cookies from wherever we ended up
    cookies = driver.get_cookies()
    print(f"\nCookies ({len(cookies)}):")
    session_cookie = None
    for c in cookies:
        print(f"  {c['name']} = {c['value'][:50]}")
        if c['name'].lower() in ('session', 'ssid', 'qx_session', 'token'):
            session_cookie = c['value']
            print(f"  *** SESSION: {c['value']} ***")
    
    # Get token from JS
    try:
        token = driver.execute_script("return window?.settings?.token ?? null;")
        print(f"\nwindow.settings.token: {token[:50] if token else 'N/A'}")
    except:
        pass
    
    if session_cookie:
        print(f"\n✅ REAL SESSION TOKEN: {session_cookie}")
        cookies_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
        ua = driver.execute_script("return navigator.userAgent")
        session_data = {
            email: {
                "cookies": cookies_str,
                "token": token or session_cookie,
                "user_agent": ua,
            }
        }
        with open("session.json", "w") as f:
            json.dump(session_data, f, indent=2)
        print("Saved to session.json")
    
    input("\nPress Enter to close...")
finally:
    driver.quit()
