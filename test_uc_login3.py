"""Test uc login - click sign-in tab, fill form, submit, capture real cookie."""
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException
import json, os, time
from dotenv import load_dotenv

load_dotenv()
email = os.getenv("QUOTEX_EMAIL")
password = os.getenv("QUOTEX_PASSWORD")

options = uc.ChromeOptions()
options.add_argument("--disable-blink-features=AutomationControlled")

driver = uc.Chrome(version_main=150, headless=False, options=options)
wait = WebDriverWait(driver, 20)

try:
    driver.get("https://market-qx.trade/en/sign-in")
    time.sleep(5)
    print(f"URL: {driver.current_url}")

    # Click the sign-in tab (data-value=1) to show sign-in form
    try:
        sign_in_tab = wait.until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, 'a.modal-sign__tab[data-value="1"]')
        ))
        sign_in_tab.click()
        print("Clicked sign-in tab")
        time.sleep(2)
    except Exception as e:
        print(f"Could not click sign-in tab: {e}")

    # Wait for the email input in tab-1 to be visible
    try:
        email_input = wait.until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, '#tab-1 input[name="email"]')
        ))
        print("Email input is interactable")
    except TimeoutException:
        print("Email input not interactable, trying JS click")
        driver.execute_script("""
            var tab = document.querySelector('a.modal-sign__tab[data-value="1"]');
            if (tab) tab.click();
        """)
        time.sleep(1)
        email_input = driver.find_element(By.CSS_SELECTOR, '#tab-1 input[name="email"]')

    # Get CSRF
    csrf = driver.find_element(By.CSS_SELECTOR, '#tab-1 input[name="_token"]').get_attribute("value")
    print(f"CSRF: {csrf[:30]}...")

    # Fill form
    email_input.clear()
    email_input.send_keys(email)
    
    pwd_input = driver.find_element(By.CSS_SELECTOR, '#tab-1 input[name="password"]')
    pwd_input.clear()
    pwd_input.send_keys(password)

    # Check for Turnstile widget
    turnstile = driver.find_elements(By.CSS_SELECTOR, '.cf-turnstile, iframe[src*="challenges.cloudflare.com"]')
    print(f"Turnstile widgets: {len(turnstile)}")

    # Submit
    submit_btn = driver.find_element(By.CSS_SELECTOR, '#tab-1 button.modal-sign__block-button')
    submit_btn.click()
    print("Form submitted")

    time.sleep(15)
    print(f"After login URL: {driver.current_url}")
    print(f"Page title: {driver.title}")

    # If we're still on sign-in, maybe something blocked us
    if "sign-in" in driver.current_url or "sign-in" in driver.page_source.lower()[:500]:
        print("Still on sign-in page - checking for errors")
        body_text = driver.find_element(By.TAG_NAME, "body").text[:1000]
        print(f"Body text: {body_text}")

        # Check for validation errors
        errors = driver.find_elements(By.CSS_SELECTOR, '.modal-sign__error, .error, .alert, .invalid-feedback')
        for e in errors:
            print(f"Error: {e.text}")

        # Try submitting via JS directly
        print("\nTrying JS form submission...")
        driver.execute_script("""
            var form = document.querySelector('#tab-1 form');
            if (form) {
                form.submit();
            }
        """)
        time.sleep(10)
        print(f"After JS submit URL: {driver.current_url}")
    else:
        print("LOGIN SUCCESSFUL!")
        
        # Navigate to trade page
        driver.get("https://market-qx.trade/en/trade")
        time.sleep(5)
        print(f"Trade page URL: {driver.current_url}")

    # Get cookies anyway
    cookies = driver.get_cookies()
    print(f"\nCookies ({len(cookies)}):")
    session_cookie = None
    for c in cookies:
        print(f"  {c['name']} = {c['value'][:50]}")
        if c['name'].lower() in ('session', 'ssid', 'qx_session', 'token'):
            session_cookie = c['value']
            print(f"  *** FOUND: {c['name']} = {c['value']} ***")

    # Get token from JS
    try:
        token = driver.execute_script("return window?.settings?.token ?? null;")
        print(f"\nwindow.settings.token: {token[:50] if token else 'N/A'}")
    except:
        token = None

    if session_cookie or token:
        real_token = session_cookie or token
        print(f"\n✅ REAL TOKEN: {real_token}")
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
        print("✅ Saved to session.json")

    input("\nPress Enter to close...")
finally:
    driver.quit()
