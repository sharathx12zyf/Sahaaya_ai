"""Settings. The app starts WITHOUT any keys; AI features then report 'key not set'."""
import os

DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))
os.makedirs(DATA_DIR, exist_ok=True)


def _load_dotenv():
    path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()


def key_status() -> dict:
    return {"sarvam": bool(os.environ.get("SARVAM_API_KEY")),
            "nvidia": bool(os.environ.get("NVIDIA_API_KEY"))}


def llm_order() -> list[str]:
    s = key_status()
    return [p for p in ("sarvam", "nvidia") if s[p]]


class KeyNotSet(Exception):
    pass


def require_keys(voice: bool = False):
    s = key_status()
    if voice and not s["sarvam"]:
        raise KeyNotSet("SARVAM_API_KEY not set: voice features are disabled. Add it to .env and restart.")
    if not (s["sarvam"] or s["nvidia"]):
        raise KeyNotSet("AI key not set (SARVAM_API_KEY or NVIDIA_API_KEY). Add one to .env and restart.")
