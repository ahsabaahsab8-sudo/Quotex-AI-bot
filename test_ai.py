import openai, json
client = openai.OpenAI(
    base_url='https://opencode.ai/zen/v1',
    api_key='sk-5UVZdq3bAXTbOm55FiX8LqZIy4gKz2VFs5MVdU7QFfsqXQ8evXzVDU3Y0Tc5qY32',
    timeout=30
)
try:
    r = client.chat.completions.create(
        model='deepseek-v4-flash-free',
        messages=[{'role':'user','content':'Say hi in JSON format with key "answer"'}],
        temperature=0.2,
        max_tokens=100
    )
    print('SUCCESS:', r.choices[0].message.content[:300])
except Exception as e:
    print('FAILED:', str(e)[:500])
