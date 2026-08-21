import os, time
from dotenv import load_dotenv
load_dotenv()
from openai import OpenAI

key = os.getenv("KILO_API_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJlbnYiOiJwcm9kdWN0aW9uIiwia2lsb1VzZXJJZCI6ImQyYjRjOTIwLTYwYTAtNGQwZS04ZjliLWQ4MDAyNjI5MzIwMCIsImFwaVRva2VuUGVwcGVyIjpudWxsLCJ2ZXJzaW9uIjozLCJpYXQiOjE3ODY1MTk4MjEsImV4cCI6MTk0NDE5OTgyMX0.WhsCfQWhMCyJzeacsekuRTurBjqQr6iEUwx4ln-SK34")
c = OpenAI(base_url="https://api.kilo.ai/api/gateway", api_key=key, timeout=60)

msg = {"role": "user", "content": 'Reply with only valid JSON {"status": "ok"}'}
for model in [
    "nvidia/nemotron-3.5-lightning:free",
    "poolside/laguna-s-2.1:free",
    "cohere/north-mini-code:free",
    "liquid/lfm-2.5-2.6b:free",
    "stepfun/step-3.7-flash:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
]:
    try:
        t0 = time.time()
        r = c.chat.completions.create(model=model, messages=[msg], max_tokens=100)
        print(model, "->", round(time.time() - t0, 1), "s", repr((r.choices[0].message.content or "")[:60]))
    except Exception as e:
        print(model, "ERR", type(e).__name__, str(e)[:120])