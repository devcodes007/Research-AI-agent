"""Model-agnostic LLM access via LiteLLM. Any provider works by changing the model string in .env."""
import json
import re
import threading
import time

from .config import env

_lock = threading.Lock()
_last = [0.0]
_backend = None  # tests inject a fake with set_backend()
HANDOFF = "handoff"


class NeedsAnswer(Exception):
    """Handoff mode: a prompt was written and is waiting for an agent (any model, any tool) to answer it."""


def label(model: str) -> str:
    """Human-readable model name stored in records (handoff mode records who actually answered)."""
    return env("ATLAS_HANDOFF_LABEL", "external agent (file handoff)") if model == HANDOFF else model


def handoff_dir():
    from .config import sub
    return sub("handoff")


def set_backend(fn):
    global _backend
    _backend = fn


def _throttle():
    """Stay under free-tier requests-per-minute limits."""
    rpm = float(env("ATLAS_RPM", "8"))
    with _lock:
        wait = _last[0] + 60.0 / rpm - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.monotonic()


def complete(model: str, system: str, user: str, max_tokens: int = 3500, key: str = None) -> str:
    if _backend is not None:
        return _backend(model, system, user)
    if model == HANDOFF:
        folder = handoff_dir()
        answer = folder / f"{key}.answer.json"
        if answer.exists() and answer.stat().st_size > 2:
            return answer.read_text(encoding="utf-8-sig")
        (folder / f"{key}.prompt.md").write_text(
            f"# TASK {key}\nYou are the LLM step of the Toolkit Atlas pipeline. Follow the SYSTEM and USER text below exactly.\n"
            f"Write ONLY the JSON object to: data/handoff/{key}.answer.json\n\n## SYSTEM\n{system}\n\n## USER\n{user}\n", encoding="utf-8")
        raise NeedsAnswer(key)
    import litellm
    litellm.drop_params = True
    _throttle()
    resp = litellm.completion(model=model, temperature=0, max_tokens=max_tokens, num_retries=5,
                              response_format={"type": "json_object"},
                              messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
    return resp.choices[0].message.content or ""


def parse_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(text)
    except ValueError:
        a, b = text.find("{"), text.rfind("}")
        if a >= 0 and b > a:
            return json.loads(text[a:b + 1])
        raise


def ask_json(model: str, system: str, user: str, retries: int = 2, key: str = None) -> dict:
    """Call the model and parse JSON; on malformed output, retry with the parse error (bounded)."""
    last = None
    retries = 0 if model == HANDOFF else retries
    for attempt in range(retries + 1):
        prompt = user if attempt == 0 else user + f"\n\nYour previous reply was not valid JSON ({last}). Reply with ONLY one JSON object."
        raw = complete(model, system, prompt, key=key)
        try:
            return parse_json(raw)
        except ValueError as exc:
            last = str(exc)[:120]
    raise ValueError(f"model returned invalid JSON after {retries + 1} attempts: {last}")
