# Quotex Signal Bot - Session Context (Saved 2026-07-28)
# After PC restart, tell the AI: "read the session notes"

## Setup
- Project: C:\Users\PC\Desktop\Quotex Signal
- Python: .venv\Scripts\python.exe (Python 3.14)
- A11ksa library: A11ksa_API_Quotex (pip install -e)
- websockets pinned to 13.1 (not 16.x)

## What Works
1. **REST API login**: `POST https://market-quotex.pro/api/v1/sign-in` with curl_cffi returns a session token, but it's a GUEST token (always returns "Bad request" error, even with wrong credentials). NOT valid for WebSocket.
2. **WebSocket connects**: A11ksa connects to `wss://ws2.market-quotex.pro/socket.io/?EIO=3&transport=websocket` successfully.
3. **Server pushes instruments/list** immediately after Socket.IO connect, BEFORE auth validation completes.
4. **A11ksa handshake fixed**: `_send_handshake` in `websocket_client.py` now properly waits for `s_authorization` (success) or `authorization/reject` (failure) instead of treating `instruments/list` as success.

## What's Blocked
1. **WebSocket auth fails**: Server sends `42["authorization/reject"]` then `41` (disconnect) after we send our auth message. The token from the REST API is rejected.
2. **qxbroker.com geo-blocked**: Shows "Not available in your region". Login form is behind Cloudflare + geo-block.
3. **market-quotex.pro/en/sign-in**: Behind Cloudflare. Playwright can get `cf_clearance` cookie but still hits Cloudflare challenge.
4. **All API endpoints except `/api/v1/sign-in`**: Return Cloudflare challenge HTML (not JSON).

## Key Files Modified
- `quotex_adapter.py` - Main adapter wrapping A11ksa client
- `A11ksa_API_Quotex/api_quotex/websocket_client.py` - Fixed `_send_handshake` to wait for real auth result; fixed `"40"` handling; changed `DEFAULT_HEADERS` Origin/Referer to market-quotex.pro
- `A11ksa_API_Quotex/api_quotex/constants.py` - Updated DEFAULT_HEADERS to market-quotex.pro

## What Needs to Happen Next
The main blocker: getting a VALID authenticated SSID token.
- The REST API at `/api/v1/sign-in` returns guest tokens only.
- Need to use form-based login or find the real auth API.
- PROBABLE CAUSE: VPN was on, IP in blocked region. The "Bad request" error on the API and geo-block on qxbroker.com are both due to VPN IP.

## Next Steps (in order)
1. Disconnect VPN, restart PC
2. Run: `.venv\Scripts\python.exe test_adapter.py` - see if API returns valid token
3. If token still has "Bad request" error, try A11ksa's built-in `get_ssid()` function
4. If qxbroker.com works without VPN, modify `A11ksa_API_Quotex/api_quotex/constants.py` to restore `Origin: https://qxbroker.com` and `Referer: https://qxbroker.com/`
5. Verify end-to-end: connect → auth → fetch candles → indicators → signals

## Test Files
- `test_adapter.py` - Main integration test
- `test_ws_handshake.py` - Raw WebSocket auth test
- `debug_api_*.py` - Various API debugging scripts
