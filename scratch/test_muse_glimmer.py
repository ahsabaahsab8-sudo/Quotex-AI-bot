"""Test the new Nvidia model meta/muse-glimmer-30b (basic + chart image analysis)."""
import asyncio, base64, json, logging, sys, os, time
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from openai import OpenAI

NVIDIA_API_KEY = "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"
client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=NVIDIA_API_KEY)


async def basic_test():
    print("=== TEST 1: Basic model response ===")
    start = time.time()
    completion = await asyncio.to_thread(
        client.chat.completions.create,
        model="meta/muse-glimmer-30b",
        messages=[
            {"role": "system", "content": "You are a precise quantitative trading assistant. Output ONLY valid JSON. Start with '{' and end with '}'."},
            {"role": "user", "content": 'Return {"status":"ok","message":"working"}'}
        ],
        temperature=0.2, top_p=0.7, max_tokens=200,
        response_format={"type": "json_object"}
    )
    elapsed = time.time() - start
    content = completion.choices[0].message.content.strip()
    print(f"SUCCESS in {elapsed:.1f}s: {content}")
    return content


async def chart_test():
    import main as m
    print("=== TEST 2: Chart image analysis (real candlestick chart) ===")
    with open('scratch/test_render_chart.png', 'rb') as f:
        b64 = base64.b64encode(f.read()).decode()

    tech_data = {"analysis_timeframe_seconds": 60, "analysis_timeframe_label": "1m",
                 "metrics_1m": {"trend": "bullish", "macd_diff": 0.5, "rsi": 55},
                 "ema_alignment": "BULLISH_ALIGNED", "adx": 28, "adx_strength": "strong"}

    print('>>> Calling query_glm_analysis (meta/muse-glimmer-30b) with chart image ...')
    r = await m.query_glm_analysis(tech_data, chart_b64=b64)
    print('>>> RESULT:', json.dumps(r, indent=2) if r else None)
    if isinstance(r, dict) and r.get("chart_analysis"):
        print('>>> CHART ANALYSIS PRESENT: OK')
    else:
        print('>>> CHART ANALYSIS MISSING (maybe schema rejected chart_analysis)')


asyncio.run(basic_test())
print()
asyncio.run(chart_test())
