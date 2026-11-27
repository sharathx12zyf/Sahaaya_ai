"""Settings. The app starts WITHOUT any keys; AI features then report 'key not set'."""
import os
import time

# Businesses are in India: all schedules, "today" and "now" use India time, whatever the server's clock zone.
os.environ.setdefault("TZ", "Asia/Kolkata")
if hasattr(time, "tzset"):
    time.tzset()

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


# ---- is the voice service actually usable (credits left)? checked at most every 5 minutes ----
_VOICE = {"ok": None, "at": 0.0, "why": ""}


def voice_service_ok(force: bool = False) -> bool:
    import requests
    if not os.environ.get("SARVAM_API_KEY"):
        _VOICE.update(ok=False, why="SARVAM_API_KEY not set")
        return False
    if not force and _VOICE["ok"] is not None and time.time() - _VOICE["at"] < 300:
        return _VOICE["ok"]
    try:
        r = requests.post("https://api.sarvam.ai/text-to-speech", timeout=15,
                          headers={"api-subscription-key": os.environ["SARVAM_API_KEY"]},
                          json={"text": "ok", "target_language_code": "en-IN"})
        ok = r.status_code == 200
        why = "" if ok else (r.json().get("error", {}).get("message", f"HTTP {r.status_code}") if r.headers.get(
            "content-type", "").startswith("application/json") else f"HTTP {r.status_code}")
    except Exception as e:
        ok, why = False, e.__class__.__name__
    _VOICE.update(ok=ok, at=time.time(), why=why)
    return ok


def voice_service_reason() -> str:
    return _VOICE["why"]


def mark_voice_down(why: str):
    _VOICE.update(ok=False, at=time.time(), why=why)
