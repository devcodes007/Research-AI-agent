"""Configuration: paths and environment. Reads an optional .env file (no extra dependency)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_dotenv():
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


def env(key, default=None):
    value = os.environ.get(key)
    return value if value not in (None, "") else default


def data_dir() -> Path:
    """Data root; overridable so tests and demos never touch the real dataset."""
    return Path(env("ATLAS_DATA", str(ROOT / "data")))


def sub(name: str) -> Path:
    path = data_dir() / name
    path.mkdir(parents=True, exist_ok=True)
    return path


# Model strings are LiteLLM model names, so any provider works:
#   gemini/gemini-2.5-flash, groq/llama-3.3-70b-versatile, ollama/qwen2.5:14b,
#   openrouter/<model>, anthropic/<model>, openai/<model> ...
def model_primary():
    return env("ATLAS_MODEL", "handoff")


def model_verify():
    """Second, preferably different, model for the blind verification pass."""
    return env("ATLAS_VERIFY_MODEL", model_primary())


def model_adjudicate():
    return env("ATLAS_ADJUDICATE_MODEL", model_verify())
