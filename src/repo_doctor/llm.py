
from openai import OpenAI
from .config import settings
import os

client = OpenAI(
    api_key = settings.deepseek_api_key,
    base_url="https://api.deepseek.com",
)

def call_llm(messages, tools_schema=None, temperature=0.0):
    response = client.chat.completions.create(
        model=settings.model,
        messages=messages,
        tools=tools_schema or None,
        temperature=temperature,
    )
    return response.choices[0].message