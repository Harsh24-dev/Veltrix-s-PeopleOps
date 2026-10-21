import json

from app.config import get_settings

_MODEL_PREFIX = {"openai": "", "anthropic": "anthropic/", "gemini": "gemini/"}


def available() -> bool:
    return bool(get_settings().provider_key())


def complete(system: str, user: str, json_mode: bool = False) -> str:
    settings = get_settings()
    if not settings.provider_key():
        return ""
    import litellm

    model = _MODEL_PREFIX.get(settings.llm_provider, "") + settings.llm_model
    kwargs = {"temperature": 0, "api_key": settings.provider_key()}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    resp = litellm.completion(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        **kwargs,
    )
    return resp["choices"][0]["message"]["content"]


def complete_schema(system: str, user: str, schema: dict) -> dict:
    """Constrained structured output: force the model to a strict JSON schema
    (grammar-constrained decoding). Falls back to plain JSON mode if the
    provider rejects json_schema."""
    settings = get_settings()
    if not settings.provider_key():
        return {}
    import litellm

    model = _MODEL_PREFIX.get(settings.llm_provider, "") + settings.llm_model
    fmt = {"type": "json_schema", "json_schema": {"name": "intent", "strict": True, "schema": schema}}
    try:
        resp = litellm.completion(
            model=model, temperature=0, api_key=settings.provider_key(),
            response_format=fmt,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        return _parse(resp["choices"][0]["message"]["content"])
    except Exception:
        return complete_json(system, user)


def complete_json(system: str, user: str) -> dict:
    """Ask for JSON and tolerate the usual stray fences / trailing text."""
    return _parse(complete(system, user, json_mode=True))


def _parse(raw: str) -> dict:
    raw = (raw or "").strip()
    if not raw:
        return {}
    if raw.startswith("```"):
        raw = raw.strip("`").split("\n", 1)[-1]
    start, end = raw.find("{"), raw.rfind("}")
    try:
        return json.loads(raw[start : end + 1])
    except (ValueError, json.JSONDecodeError):
        return {}
