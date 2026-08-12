"""
Diagnostic: List all models from Kilo Code API gateway and test free fast ones.
Correct base URL: https://api.kilo.ai/api/gateway
Models list (no auth needed): https://api.kilo.ai/api/gateway/models
"""
import os, sys, time, json
import urllib.request, urllib.error

KILO_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJlbnYiOiJwcm9kdWN0aW9uIiwia2lsb1VzZXJJZCI6ImQyYjRjOTIwLTYwYTAtNGQwZS04ZjliLWQ4MDAyNjI5MzIwMCIsImFwaVRva2VuUGVwcGVyIjpudWxsLCJ2ZXJzaW9uIjozLCJpYXQiOjE3ODY1MTk4MjEsImV4cCI6MTk0NDE5OTgyMX0.WhsCfQWhMCyJzeacsekuRTurBjqQr6iEUwx4ln-SK34"
BASE_URL = "https://api.kilo.ai/api/gateway"
MODELS_URL = "https://api.kilo.ai/api/gateway/models"

print("=" * 65)
print("Kilo Code Gateway — Full Model List")
print(f"Fetching: {MODELS_URL}")
print("=" * 65)

# ── 1. Fetch model list (no auth needed) ─────────────────────────────────
try:
    req = urllib.request.Request(MODELS_URL, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read().decode("utf-8")
    data = json.loads(raw)
except Exception as e:
    print(f"ERROR fetching models: {e}")
    sys.exit(1)

# The response may be {"data": [...]} or a plain list
models_list = data.get("data", data) if isinstance(data, dict) else data
print(f"\nTotal models available: {len(models_list)}\n")

# Print all with pricing indicator
free_models = []
for m in models_list:
    mid = m.get("id", m.get("name", "?"))
    price_in  = m.get("pricing", {}).get("prompt",     m.get("inputPrice",  None))
    price_out = m.get("pricing", {}).get("completion", m.get("outputPrice", None))
    ctx       = m.get("context_length", m.get("contextLength", "?"))
    is_free   = (price_in == 0 or price_in == "0" or price_in is None and price_out in (0, "0"))
    tag = "[FREE?]" if is_free else ""
    print(f"  {mid:<60} ctx={ctx}  in={price_in} out={price_out} {tag}")
    if is_free:
        free_models.append(mid)

print(f"\n\nModels with $0 / free pricing: {len(free_models)}")
for m in free_models:
    print(f"  FREE: {m}")

# ── 2. Test candidate fast free models (no step models) ──────────────────
from openai import OpenAI

client = OpenAI(base_url=BASE_URL, api_key=KILO_KEY, timeout=40.0)

KEYWORDS = ["nemotron", "llama", "qwen", "mistral", "flash", "mini", "nano",
            "deepseek", "gemma", "phi", "hermes", "zephyr", "dolphin",
            "free", "lite", "small"]
EXCLUDE  = ["step", "o1", "o3", "claude-opus", "gpt-4o-2024", "vision"]

candidates = [
    m.get("id", m.get("name", "?"))
    for m in models_list
    if any(kw in m.get("id", m.get("name","")).lower() for kw in KEYWORDS)
    and not any(ex in m.get("id", m.get("name","")).lower() for ex in EXCLUDE)
]

# Also include any explicitly free ones found above
for mid in free_models:
    if mid not in candidates and not any(ex in mid.lower() for ex in EXCLUDE):
        candidates.append(mid)

candidates = list(dict.fromkeys(candidates))  # deduplicate

print(f"\n\n{'='*65}")
print(f"Quick-testing {min(len(candidates),18)} candidate models for speed...")
print("="*65)

SIMPLE_MSG = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user",   "content": "Reply with just the word: WORKING"}
]

results = []
for model_id in candidates[:18]:
    t0 = time.time()
    try:
        resp = client.chat.completions.create(
            model=model_id,
            messages=SIMPLE_MSG,
            temperature=0.0,
            max_tokens=20,
        )
        elapsed = time.time() - t0
        text = (resp.choices[0].message.content or "").strip()[:40] if resp.choices else ""
        status = "OK"
        print(f"  OK  {elapsed:5.1f}s  {model_id:<60}  reply={text!r}")
    except Exception as e:
        elapsed = time.time() - t0
        status = "FAIL"
        err = str(e)[:80]
        print(f"  ERR {elapsed:5.1f}s  {model_id:<60}  {err}")
    results.append((elapsed, model_id, status))

print(f"\n\n{'='*65}")
print("SUMMARY — Working models sorted fastest first:")
print("="*65)
working = [(t, mid) for t, mid, s in results if s == "OK"]
working.sort()
for t, mid in working:
    print(f"  {t:.1f}s  {mid}")

print(f"\nDone. ({len(working)}/{len(candidates[:18])} responded OK)")
