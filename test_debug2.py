import os, json, sys

# Test the actual path resolution from the script location
script = r"C:\Users\PC\Desktop\Quotex Signal\skills\quotex-trader\scripts\fetch_candles.py"
root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(script)))))
print(f"PROJECT_ROOT: {root}")

path = os.path.join(root, "session.json")
print(f"Session path: {path}")
print(f"Exists: {os.path.exists(path)}")

if os.path.exists(path):
    with open(path) as f:
        data = json.load(f)
    print(f"Keys: {list(data.keys())}")

email = os.environ.get("QUOTEX_EMAIL", "NOT SET")
print(f"QUOTEX_EMAIL from env: '{email}'")
