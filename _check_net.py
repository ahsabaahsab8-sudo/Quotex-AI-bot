import httpx
import sys

print("Testing Telegram API connectivity...")

# Try with default client
try:
    with httpx.Client(timeout=15) as client:
        r = client.get('https://api.telegram.org/bot8858446215:AAGhIF-GEdaFjL2qdKokcpo2xFdEPt5s5KQ/getMe')
        print(f"Default: Status={r.status_code}, ok={r.json().get('ok')}")
except Exception as e:
    print(f"Default: {type(e).__name__}: {e}")

# Try with resolved IPv4
try:
    import socket
    ip = socket.getaddrinfo('api.telegram.org', 443, socket.AF_INET)[0][4][0]
    print(f"IPv4 resolved: {ip}")
    with httpx.Client(timeout=15, transport=httpx.HTTPTransport(local_address='0.0.0.0')) as client:
        r = client.get(f'https://{ip}/bot8858446215:AAGhIF-GEdaFjL2qdKokcpo2xFdEPt5s5KQ/getMe', headers={'Host': 'api.telegram.org'})
        print(f"IPv4: Status={r.status_code}")
except Exception as e:
    print(f"IPv4: {type(e).__name__}: {e}")

print("Done")
