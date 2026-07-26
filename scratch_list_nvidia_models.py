import os
import sys
from openai import OpenAI
from dotenv import load_dotenv

# Force standard stdout encoding
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()
api_key = "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"
client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=api_key
)

try:
    print("Fetching models from Nvidia API...")
    models = client.models.list()
    print("Available Models:")
    for model in models.data:
        print(f"- {model.id}")
except Exception as e:
    print(f"Error listing models: {e}")
