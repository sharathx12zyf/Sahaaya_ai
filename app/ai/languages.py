import re

"""Language codes + script-based detection (very reliable for native-script text)."""

NAMES = {
    "en": "English", "hi": "Hindi", "kn": "Kannada", "te": "Telugu", "ta": "Tamil",
    "ml": "Malayalam", "mr": "Marathi", "bn": "Bengali", "gu": "Gujarati",
    "pa": "Punjabi", "or": "Odia",
}

# Unicode block -> language
_RANGES = [
    (0x0C80, 0x0CFF, "kn"), (0x0C00, 0x0C7F, "te"), (0x0B80, 0x0BFF, "ta"),
    (0x0D00, 0x0D7F, "ml"), (0x0900, 0x097F, "hi"), (0x0980, 0x09FF, "bn"),
    (0x0A80, 0x0AFF, "gu"), (0x0A00, 0x0A7F, "pa"), (0x0B00, 0x0B7F, "or"),
]

GREETINGS = {
    "kn": "ನಮಸ್ಕಾರ, {biz} ಗೆ ಸ್ವಾಗತ. ನಾನು {agent}. ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ? ನೀವು ಯಾವುದೇ ಭಾಷೆಯಲ್ಲಿ ಮಾತನಾಡಬಹುದು.",
    "hi": "नमस्ते, {biz} में आपका स्वागत है। मैं {agent} बोल रही हूँ। मैं आपकी क्या मदद कर सकती हूँ? आप किसी भी भाषा में बात कर सकते हैं।",
    "en": "Hello, welcome to {biz}. This is {agent}, an assistant. How can I help you? You can speak in any language.",
    "te": "నమస్కారం, {biz} కి స్వాగతం. నేను {agent}. మీకు ఎలా సహాయం చేయగలను? మీరు ఏ భాషలోనైనా మాట్లాడవచ్చు.",
    "ta": "வணக்கம், {biz} க்கு வரவேற்கிறோம். நான் {agent}. உங்களுக்கு எப்படி உதவலாம்? நீங்கள் எந்த மொழியிலும் பேசலாம்.",
}


def detect_script_language(text: str, fallback: str = "en") -> str:
    counts: dict[str, int] = {}
    latin = 0
    for ch in text:
        cp = ord(ch)
        if ch.isascii() and ch.isalpha():
            latin += 1
            continue
        for lo, hi, code in _RANGES:
            if lo <= cp <= hi:
                counts[code] = counts.get(code, 0) + 1
                break
    if counts:
        return max(counts, key=counts.get)
    return "en" if latin else fallback


def foreign_script(text: str, lang: str) -> bool:
    """True if text contains letters of an Indian script other than lang's (e.g. Kannada inside Tamil)."""
    for ch in text:
        cp = ord(ch)
        for lo, hi, code in _RANGES:
            if lo <= cp <= hi and code != lang and not (code == "hi" and lang == "mr"):
                return True
    return False


# Romanised Indian languages typed or transcribed in English letters ("mera phone kharab hai", "naale barteeni").
_ROMAN = {
    "hi": {"hai", "hain", "mera", "meri", "mere", "kya", "kyun", "nahi", "nahin", "bhaiya", "bhai", "kal", "aaj", "naam",
           "ho", "gaya", "gayi", "karo", "kar", "kitna", "kitne", "paisa", "kab", "sham", "subah", "raat", "chahiye",
           "theek", "thik", "accha", "achha", "haan", "ji", "aap", "hum", "kaise", "kuch", "abhi", "baad", "lagega"},
    "kn": {"naale", "nale", "ivattu", "ide", "illa", "beku", "beda", "maadi", "madi", "banni", "barthini", "bartini",
           "hesaru", "nanna", "nimma", "yaake", "yake", "eshtu", "ellide", "aagtilla", "agtilla", "sari", "houdu",
           "howdu", "swalpa", "guru", "saar", "sanje", "beligge", "ratri", "aaytu", "ayitu", "gottilla"},
    "te": {"naa", "nenu", "meeru", "ledu", "undi", "unnayi", "cheyyandi", "cheyandi", "repu", "ippudu", "enti", "emiti",
           "entha", "ela", "peru", "raavachha", "ravacha", "saayantram", "udayam", "avunu", "kaadu", "kavali", "baagundi"},
}


def detect_romanized(text: str) -> str | None:
    """Return hi/kn/te if a Latin-script sentence is really Hinglish/Kanglish/Tenglish, else None."""
    words = re.findall(r"[a-z]+", text.lower())
    if not words:
        return None
    score = {k: sum(w in v for w in words) for k, v in _ROMAN.items()}
    best = max(score, key=score.get)
    return best if score[best] >= 2 or (score[best] == 1 and len(words) <= 4) else None
