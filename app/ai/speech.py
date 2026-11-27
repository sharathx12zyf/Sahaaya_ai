"""Sarvam speech: Saarika (speech->text, auto language) and Bulbul (text->speech)."""
import base64
import os
import re
import shutil
import subprocess

import requests

BASE = "https://api.sarvam.ai"
# our short codes -> Sarvam BCP-47 codes
SARVAM_LANG = {"en": "en-IN", "hi": "hi-IN", "kn": "kn-IN", "te": "te-IN", "ta": "ta-IN",
               "ml": "ml-IN", "mr": "mr-IN", "bn": "bn-IN", "gu": "gu-IN", "pa": "pa-IN", "or": "od-IN"}
SHORT = {v: k for k, v in SARVAM_LANG.items()}


def _h():
    return {"api-subscription-key": os.environ["SARVAM_API_KEY"]}


def _kind(data: bytes) -> tuple[str, str]:
    if data[:4] == b"RIFF":
        return "a.wav", "audio/wav"
    if data[:4] == b"OggS":
        return "a.ogg", "audio/ogg"
    if data[:4] == b"\x1aE\xdf\xa3":
        return "a.webm", "audio/webm"
    if data[4:8] == b"ftyp":
        return "a.mp4", "audio/mp4"
    return "a.mp3", "audio/mpeg"


def prepare(data: bytes) -> tuple[str, bytes, str]:
    """Clean up audio with ffmpeg if it is installed (noise filter, 16 kHz); otherwise send as is
    (Sarvam accepts browser webm/ogg/mp4 directly)."""
    if shutil.which("ffmpeg"):
        try:
            return "a.wav", to_wav16k(data), "audio/wav"
        except Exception:
            pass
    name, mime = _kind(data)
    return name, data, mime


def to_wav16k(data: bytes) -> bytes:
    """Any browser/phone audio (webm, ogg, 8k wav) -> 16 kHz mono wav with light noise filtering."""
    p = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", "pipe:0", "-ar", "16000", "-ac", "1",
                        "-af", "highpass=f=80,afftdn=nf=-25", "-f", "wav", "pipe:1"],
                       input=data, capture_output=True, check=True)
    return p.stdout


def transcribe_smart(audio: bytes, call_lang: str) -> dict:
    """Auto-detect first. If an Indian-language call comes back as English letters (e.g. Tamil
    written as 'En phone repair achha'), listen again with the call's language as a hint."""
    from .languages import detect_script_language
    h = transcribe(audio)
    if call_lang != "en" and h["lang"] == "en" and h["text"]:
        words = re.findall(r"[A-Za-z]+", h["text"])
        common = {"phone", "order", "kyc", "repair", "battery", "screen", "laptop", "ok", "okay", "status", "refund",
                  "slot", "time", "tomorrow", "today", "pending", "verify", "link", "yes", "no", "hello", "sir"}
        english = sum(w.lower() in common for w in words)
        if words and english / len(words) < 0.6:
            h2 = transcribe(audio, call_lang)
            if h2["text"] and detect_script_language(h2["text"], "en") == call_lang:
                return h2
    return h


def transcribe(audio: bytes, hint: str | None = None) -> dict:
    """Returns {text, lang (short code), confidence}."""
    r = requests.post(f"{BASE}/speech-to-text", headers=_h(), timeout=30,
                      files={"file": prepare(audio)},
                      data={"language_code": SARVAM_LANG.get(hint, "unknown") if hint else "unknown"})
    r.raise_for_status()
    j = r.json()
    code = j.get("language_code") or ""
    return {"text": (j.get("transcript") or "").strip(),
            "lang": SHORT.get(code, code.split("-")[0] or "en"),
            "confidence": j.get("language_probability")}


# Which voice engine each language uses. Default: Bhashini for Kannada/Hindi/Telugu when its keys are set
# (sounds most natural there), Sarvam for English. Owners can change it per language in Settings.
DEFAULT_PROVIDER = {"kn": "bhashini", "hi": "bhashini", "te": "bhashini", "en": "sarvam"}


def provider_for(lang: str, chosen: dict | None = None) -> str:
    from . import bhashini
    p = (chosen or {}).get(lang) or DEFAULT_PROVIDER.get(lang, "sarvam")
    if p == "bhashini" and not bhashini.available():
        return "sarvam"
    return p


def speak(text: str, lang: str, speaker: str | None = None, rate: int = 22050, provider: str | None = None) -> bytes:
    """Returns WAV bytes in a natural Indian voice (Bhashini or Sarvam; if one fails, the other is tried)."""
    from . import bhashini
    if provider == "bhashini" and bhashini.available():
        try:
            return bhashini.speak(text, lang)
        except Exception:
            pass                      # fall back to Sarvam
    return _sarvam_speak(text, lang, speaker, rate)


PACE = float(os.environ.get("VOICE_PACE", "1.15"))   # a little faster than default: sounds like a real call


def _sarvam_speak(text: str, lang: str, speaker: str | None = None, rate: int = 22050) -> bytes:
    body = {"text": text[:1500], "target_language_code": SARVAM_LANG.get(lang, "en-IN"),
            "speech_sample_rate": rate, "pace": PACE}
    if speaker:
        body["speaker"] = speaker
    r = requests.post(f"{BASE}/text-to-speech", headers=_h(), json=body, timeout=30)
    r.raise_for_status()
    return base64.b64decode(r.json()["audios"][0])
