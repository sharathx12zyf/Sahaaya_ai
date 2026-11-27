"""Sahaaya: multilingual voice agent for businesses.
Section 1 Service Center (bookings & repairs)  |  Section 2 Dashboard Connect (works inside your dashboard)."""
import base64
import json
import os
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import db
from .ai import speech
from .ai.agent import Agent
from .ai.languages import GREETINGS, NAMES, detect_script_language
from .config import KeyNotSet, key_status, require_keys
from .connect import core as connect
from .service_center import core as service

app = FastAPI(title="Sahaaya")
STATIC = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=STATIC), name="static")
POOL = ThreadPoolExecutor(8)
CALLS: dict[str, dict] = {}
LANGS = ["kn", "hi", "en", "te", "ta", "ml", "mr", "bn", "gu", "pa"]
REPEAT = {"kn": "ಕ್ಷಮಿಸಿ, ಸರಿಯಾಗಿ ಕೇಳಿಸಲಿಲ್ಲ. ಮತ್ತೊಮ್ಮೆ ಹೇಳುತ್ತೀರಾ?",
          "hi": "माफ़ कीजिए, ठीक से सुनाई नहीं दिया। फिर से बोलेंगे?",
          "te": "క్షమించండి, సరిగ్గా వినిపించలేదు. మళ్ళీ చెప్పగలరా?",
          "ta": "மன்னிக்கவும், சரியாக கேட்கவில்லை. மீண்டும் சொல்ல முடியுமா?",
          "en": "Sorry, I didn't catch that. Could you say it again?"}


@app.on_event("startup")
def _startup():
    db.init()
    service.seed()
    url = os.environ.get("DEMO_DASHBOARD_URL")
    if url and not connect.connection():
        try:
            connect.discover(url, os.environ.get("DEMO_DASHBOARD_KEY", "demo-key-123"))
        except Exception:
            pass


def err(e: Exception, code=400):
    return JSONResponse({"error": str(e), "key_not_set": isinstance(e, KeyNotSet)}, code)


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


@app.get("/api/status")
def status():
    return {"keys": key_status(), "languages": {k: NAMES[k] for k in LANGS},
            "demo_dashboard_url": os.environ.get("DEMO_DASHBOARD_PUBLIC_URL", "http://localhost:9000")}


# ---------------- voice helpers ----------------
def _sentences(t):
    return [p for p in re.split(r"(?<=[.!?।])\s+", t.strip()) if p] or [t]


def voice_clips(text: str, lang: str) -> list[str]:
    """Voice for the FIRST sentence only (so the caller hears it fast); the browser fetches the
    rest in parallel from /api/tts while the first one plays."""
    if not key_status()["sarvam"]:
        return []
    try:
        return [base64.b64encode(speech.speak(_sentences(text)[0], lang)).decode()]
    except Exception:
        return []


FILLERS = {
    "kn": ["ಸರಿ, ಒಂದು ನಿಮಿಷ.", "ಹಾ, ನೋಡ್ತೀನಿ.", "ಓಕೆ, ಚೆಕ್ ಮಾಡ್ತೀನಿ."],
    "hi": ["जी, एक मिनट।", "अच्छा, देखती हूँ।", "ठीक है, चेक करती हूँ।"],
    "te": ["సరే, ఒక్క నిమిషం.", "అలాగే, చూస్తాను.", "ఓకే, చెక్ చేస్తాను."],
    "ta": ["சரி, ஒரு நிமிஷம்.", "சரி, பார்க்கிறேன்.", "ஓகே, செக் பண்றேன்."],
    "en": ["Sure, one moment.", "Okay, let me check.", "Alright, just a second."],
}


@app.get("/api/filler")
def filler(lang: str = "en", i: int = 0):
    """Short 'one moment' phrases, generated once and cached: played the instant the caller stops
    talking, so there is no dead silence while the agent thinks."""
    lang = lang if lang in FILLERS else "en"
    i = i % len(FILLERS[lang])
    path = os.path.join(db.DATA_DIR if hasattr(db, "DATA_DIR") else ".", f"filler_{lang}_{i}.b64")
    if os.path.exists(path):
        return {"audio": open(path).read()}
    if not key_status()["sarvam"]:
        return {"audio": None}
    try:
        a = base64.b64encode(speech.speak(FILLERS[lang][i], lang)).decode()
        open(path, "w").write(a)
        return {"audio": a}
    except Exception:
        return {"audio": None}


@app.post("/api/tts")
def tts(text: str = Form(...), lang: str = Form("en")):
    try:
        return {"audio": base64.b64encode(speech.speak(text, lang)).decode()}
    except Exception as e:
        return err(e)


def hear(audio: bytes, fallback_lang: str) -> dict:
    require_keys(voice=True)
    h = speech.transcribe_smart(audio, fallback_lang)
    if h["lang"] not in NAMES:
        h["lang"] = fallback_lang
    return h


# ---------------- calls (both sections) ----------------
@app.post("/api/call/start")
def call_start(section: str = Form(...), caller: str = Form(...), lang: str = Form("kn")):
    try:
        require_keys()
    except KeyNotSet as e:
        return err(e)
    if section == "service":
        cfg = service.settings()
        agent = Agent(service.persona(), service.tools(caller), caller, turn_rules=service.turn_rules())
        greet = GREETINGS.get(lang, GREETINGS["en"]).format(biz=cfg["name"], agent=cfg["agent_name"])
    else:
        conn = connect.connection()
        if not conn:
            return err(Exception("Connect a dashboard first (Dashboard Connect tab)."))
        tools, _guard = connect.tools(caller)
        known = connect.prefetch(caller, {t.name: t for t in tools})
        agent = Agent(connect.persona() + "\n" + known, tools, caller, turn_rules=connect.turn_rules())
        greet = GREETINGS.get(lang, GREETINGS["en"]).format(biz=conn["name"] + " support", agent="Sahaaya")
    agent.say_first(greet)
    sid = uuid.uuid4().hex[:12]
    CALLS[sid] = {"section": section, "agent": agent, "lang": lang, "caller": caller, "misheard": 0,
                  "transcript": [{"who": "agent", "text": greet, "lang": lang}]}
    return {"session": sid, "reply": greet, "lang": lang, "audio": voice_clips(greet, lang), "rest": _sentences(greet)[1:]}


@app.post("/api/call/turn")
async def call_turn(session: str = Form(...), text: str = Form(None), audio: UploadFile = File(None)):
    c = CALLS.get(session)
    if not c:
        return err(Exception("Call ended or expired. Start a new call."), 404)
    agent, t0 = c["agent"], time.time()
    n = len(agent.actions)
    try:
        if audio is not None:
            h = hear(await audio.read(), c["lang"])
            text, lang = h["text"], h["lang"]
        else:
            text = (text or "").strip()
            lang = detect_script_language(text, c["lang"])
            if lang == "en" and c["lang"] != "en" and not re.search(r"[a-zA-Z]{3,}", text):
                lang = c["lang"]
        if len(text) < 2:      # silence or noise
            c["misheard"] += 1
            reply = REPEAT.get(c["lang"], REPEAT["en"])
            if c["misheard"] >= 3:
                reply = {"kn": "ಸರಿಯಾಗಿ ಕೇಳಿಸುತ್ತಿಲ್ಲ. ನಮ್ಮ staff ನಿಮಗೆ ಮತ್ತೆ call ಮಾಡುತ್ತಾರೆ."}.get(
                    c["lang"], "The line is not clear. Our staff will call you back shortly.")
                service.create_ticket("Callback: unclear line", "caller could not be heard", c["caller"],
                                      section=c["section"])
            return {"heard": "", "reply": reply, "lang": c["lang"], "audio": voice_clips(reply, c["lang"]),
                    "actions": [], "ended": False, "timing": {"total": round(time.time() - t0, 1)}}
        c["misheard"], c["lang"] = 0, lang
        t1 = time.time()
        reply = agent.reply(text, lang)
        t2 = time.time()
    except KeyNotSet as e:
        return err(e)
    except Exception as e:     # never leave the caller in silence
        print("turn error:", repr(e))
        reply, lang, text, t1, t2 = ("Sorry, I'm having a small technical problem. A staff member will call you back.",
                                     "en", text or "", t0, time.time())
    c["transcript"] += [{"who": "caller", "text": text, "lang": lang}, {"who": "agent", "text": reply, "lang": lang}]
    clips = voice_clips(reply, lang)
    if agent.ended:
        _save(session)
    return {"heard": text, "reply": reply, "lang": lang, "audio": clips, "rest": _sentences(reply)[1:], "ended": agent.ended,
            "actions": [{"tool": a["tool"], "args": a["args"], "result": a["result"]} for a in agent.actions[n:]],
            "timing": {"listen": round(t1 - t0, 1), "think": round(t2 - t1, 1), "speak": round(time.time() - t2, 1),
                       "provider": agent.llm.last_provider}}


def _save(sid):
    c = CALLS.pop(sid, None)
    if not c or len(c["transcript"]) < 2:
        return
    masked = c["caller"][:2] + "******" + c["caller"][-2:]
    data = json.dumps(c["transcript"], ensure_ascii=False).replace(c["caller"], masked)
    acts = json.dumps(c["agent"].actions, ensure_ascii=False, default=str).replace(c["caller"], masked)
    db.run("INSERT INTO calls(id,section,caller,lang,transcript,actions) VALUES(?,?,?,?,?,?)",
           (sid, c["section"], masked, c["lang"], data, acts))


@app.post("/api/call/end")
def call_end(session: str = Form(...)):
    _save(session)
    return {"ok": True}


@app.get("/api/calls")
def calls(section: str):
    rows = db.q("SELECT * FROM calls WHERE section=? ORDER BY created DESC LIMIT 30", (section,))
    for r in rows:
        r["transcript"], r["actions"] = json.loads(r["transcript"]), json.loads(r["actions"] or "[]")
    return rows


@app.get("/api/notifications")
def notifications(section: str):
    return db.q("SELECT * FROM notifications WHERE section=? ORDER BY id DESC LIMIT 20", (section,))


# ---------------- Section 1: Service Center ----------------
@app.get("/api/service/overview")
def service_overview():
    import datetime
    today = datetime.date.today()
    days = [(today + datetime.timedelta(i)).isoformat() for i in range(3)]
    sched = {d: db.q("SELECT * FROM appointments WHERE status='booked' AND start LIKE ? ORDER BY start", (d + "%",))
             for d in days}
    free = {d: service.free_slots(d) for d in days}
    return {"settings": service.settings(), "schedule": sched, "free": free,
            "jobs": db.q("SELECT * FROM jobs"),
            "tickets": db.q("SELECT * FROM tickets WHERE section='service' ORDER BY created DESC")}


@app.post("/api/service/settings")
def service_settings(data: str = Form(...)):
    service.save_settings(json.loads(data))
    return {"ok": True}


# ---------------- Section 2: Dashboard Connect ----------------
@app.get("/api/connect")
def connect_get():
    c = connect.connection()
    if c:
        c = {**c, "api_key": "••••" + c["api_key"][-3:]}
    return {"connection": c, "rules": connect.rules(),
            "tickets": db.q("SELECT * FROM tickets WHERE section='connect' ORDER BY created DESC")}


@app.post("/api/connect")
def connect_post(base_url: str = Form(...), api_key: str = Form(...), key_header: str = Form("X-API-Key"),
                 name: str = Form("")):
    return connect.discover(base_url, api_key, key_header, name)


@app.post("/api/connect/permission")
def connect_perm(op_id: str = Form(...), permission: str = Form(...)):
    connect.set_permission(op_id, permission)
    return {"ok": True}


@app.post("/api/teach")
async def teach(text: str = Form(None), lang: str = Form("en"), audio: UploadFile = File(None)):
    try:
        require_keys(voice=audio is not None)
        if audio is not None:
            h = hear(await audio.read(), lang)
            text, lang = h["text"], h["lang"]
        else:
            lang = detect_script_language(text or "", lang)
        if not text:
            return err(Exception("Didn't hear anything, please try again."))
        out = connect.teach(text, lang)
        rb = out.get("readback", "")
        out.update(heard=text, lang=lang, audio=voice_clips(rb, lang) if out.get("ok") else [],
                   rest=_sentences(rb)[1:] if out.get("ok") else [])
        return out
    except KeyNotSet as e:
        return err(e)


@app.post("/api/rules/{rule_id}")
def rule(rule_id: int, action: str = Form(...)):
    connect.approve_rule(rule_id, approved=action == "approve", delete=action == "delete")
    return {"ok": True}
