import os, time, sys
sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv()
from openai import OpenAI

client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=os.getenv("NVIDIA_NEMOTRON_API_KEY"), timeout=30)
msg = {"role": "user", "content": 'Reply with only valid JSON {"status": "ok"}'}
for model in ["meta/llama-3.1-8b-instruct", "meta/llama-3.2-3b-instruct", "meta/llama-3.3-nemotron-super-49b-v1.5"]:
    try:
        t0 = time.time()
        r = client.chat.completions.create(model=model, messages=[msg], max_tokens=50)
        print(model, "->", round(time.time() - t0, 1), "s", repr((r.choices[0].message.content or "")[:60]))
    except Exception as e:
        print(model, "ERR", type(e).__name__, str(e)[:200], "in", round(time.time() - t0, 1), "s")