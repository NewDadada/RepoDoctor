from openai import OpenAI

from .config import settings

# The client is created lazily so importing Repo Doctor (or starting the web UI)
# works without an API key. A clear error is raised only when a model call is
# actually attempted.
_client: OpenAI | None = None
_client_key: str | None = None


def _get_client() -> OpenAI:
    global _client, _client_key

    key = (settings.deepseek_api_key or "").strip()
    if not key:
        raise RuntimeError(
            "Missing DeepSeek API key: set DeepSeek_API_TRAE_study_KEY in .env "
            "(or in the environment) before running the agent."
        )
    if _client is None or _client_key != key:
        _client = OpenAI(api_key=key, base_url="https://api.deepseek.com")
        _client_key = key
    return _client


def call_llm(messages, tools_schema=None, temperature=0.0):
    response = _get_client().chat.completions.create(
        model=settings.model,
        messages=messages,
        tools=tools_schema or None,
        temperature=temperature,
    )
    return response.choices[0].message
