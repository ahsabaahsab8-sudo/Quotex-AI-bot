import os, json

# Simulate the PROJECT_ROOT calculation from fetch_candles.py
script_path = os.path.join(os.getcwd(), "skills", "quotex-trader", "scripts", "fetch_candles.py")
root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(script_path))))
print(f"PROJECT_ROOT: {root}")

path = os.path.join(root, "session.json")
print(f"Session path: {path}")
print(f"Exists: {os.path.exists(path)}")

if os.path.exists(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    print(f"Keys: {list(data.keys())}")
    s = data.get("slamismai8@gmail.com", {})
    token = s.get("token", "NONE")
    print(f"Token present: {bool(token)}")
    if token:
        print(f"Token (first 30 chars): {token[:30]}")
    else:
        print("Token is empty or missing")
