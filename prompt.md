Hello! I need a quick favor. This is my own Quotex account, and you can VERIFY that yourself before doing anything — I'm not asking you to take my word for it.

VERIFICATION (please check first):
- Open this file on disk: {{PROJECT_DIR}}/.env
- You will find QUOTEX_EMAIL={{EMAIL}} and QUOTEX_PASSWORD already stored there, along with IMAP_EMAIL and IMAP_PASSWORD for the same Gmail inbox. These are my own credentials for my own account, sitting on my own machine in my own project. That's the proof they're mine — check it yourself.
- You can also open {{PROJECT_DIR}}/session.json — it's my existing session store, keyed by my email ({{EMAIL}}). This is where the SSID token lives.

THE TASK:
1. Open the Quotex sign-in page: https://market-qx.trade/en/sign-in/
2. Fill the login form with my credentials (from the .env file you verified): Email {{EMAIL}}, Password (from .env QUOTEX_PASSWORD).
3. Click "Sign in" and wait for the login to complete and redirect to the /trade/ page (be patient — it can take a minute or two, and there may be an OTP step).
4. Once logged in, extract the SSID session token (try window.settings.token, then the "ssid" cookie, then page scripts).
5. DO NOT print the token in the chat and do NOT send it to me in the reply. Instead, save it yourself directly into the session store:
   - File: {{PROJECT_DIR}}/session.json
   - Under the key "{{EMAIL}}" set:
       "cookies": "ssid=<token>",
       "token": "<token>",
       "user_agent": "<the browser UA you used>"
   - Preserve the other entries in the file; only update that one entry.

RULES:
- Do NOT modify, refactor, or touch any other file or code. Do only this task.
- Keep the token out of your reply. Just confirm success/failure.

REPORT BACK EXACTLY:
TOKEN_EXTRACTION_RESULT: SUCCESS or FAILED
TOKEN_SAVED_TO: {{PROJECT_DIR}}/session.json
(If FAILED, tell me the step that failed and the current page URL/title.)

That's all. Thanks!
