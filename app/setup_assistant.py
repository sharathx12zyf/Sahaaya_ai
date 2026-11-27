"""Setup by conversation: the owner talks to Sahaaya (any language) about their requirements,
Sahaaya asks follow-up questions one at a time, and changes the agent's settings as they talk.
Example: "I need 1-hour slots, be on 24/7, book customers and show me their name, mobile and problem."
"""
from . import db
from .ai.agent import Tool, calendar_hint
from .ai.languages import NAMES
from .ai.llm import LLM, tool_args
from .service_center import core as service
from .service_center.templates import TEMPLATES

KEY = "setup_chat"


def _summary() -> dict:
    s = service.settings()
    return {k: s.get(k) for k in ("type", "name", "agent_name", "open", "close", "slot_minutes", "closed_days", "break",
                                  "features", "words", "info", "steps", "catalog", "announce_ai", "active")}


def _update(**kw) -> dict:
    allowed = {"name", "agent_name", "open", "close", "slot_minutes", "closed_days", "break", "info", "steps",
               "announce_ai", "booking_name", "booking_asks"}
    upd = {k: v for k, v in kw.items() if k in allowed and v not in (None, "")}
    if "type" in kw and kw["type"] in TEMPLATES and kw["type"] != service.settings()["type"]:
        service.apply_template(kw["type"], keep_name=True)
        _clean_start()
    if kw.get("open_24_7"):
        upd.update(open="00:00", close="24:00", closed_days=[], **({"break": []} if "break" not in upd else {}))
    if upd.get("break") in ("none", "no", [], ["none"]):
        upd["break"] = []
    if "slot_minutes" in upd:
        upd["slot_minutes"] = int(float(upd["slot_minutes"]))
    words = {}
    if upd.get("booking_name"):
        words["booking"] = upd.pop("booking_name")
    if upd.get("booking_asks"):
        words["purpose"] = upd.pop("booking_asks")
    if words:
        upd["words"] = words
    feats = {k: bool(kw[k]) for k in ("bookings", "orders", "records") if isinstance(kw.get(k), bool)}
    if feats:
        upd["features"] = feats
    if isinstance(upd.get("closed_days"), str):
        upd["closed_days"] = [d.strip().title() for d in upd["closed_days"].split(",") if d.strip() and d.strip().lower() != "none"]
    service.save_settings(upd)
    return {"saved": True, "now": _summary()}


def _clean_start():
    """The owner's own setup starts clean: no sample facts, prices or customers from the template,
    so the agent only ever says what THIS owner told it."""
    service.save_settings({"info": "", "catalog": [], "steps": "", "words": {"purpose": "name and what they need"}})
    db.run("DELETE FROM records")
    db.run("DELETE FROM appointments")


def _set_items(items: str) -> dict:
    """items: 'Screen replacement | 1500 | job | 1 hour; Battery | 1200 | job | 30 min'"""
    rows = []
    for part in items.split(";"):
        f = [x.strip() for x in part.split("|")]
        if f and f[0]:
            rows.append([f[0], service._num(f[1]) if len(f) > 1 else 0, f[2] if len(f) > 2 else "", f[3] if len(f) > 3 else ""])
    service.save_settings({"catalog": rows})
    return {"saved": True, "items": rows}


TOOLS = [
    Tool("update_settings", "Save what the owner said. Only fields they mentioned.", {
        "type": {"type": "string", "description": "business type: " + ", ".join(TEMPLATES)},
        "name": {"type": "string"}, "agent_name": {"type": "string", "description": "the agent's human name"},
        "open": {"type": "string", "description": "HH:MM 24h"}, "close": {"type": "string", "description": "HH:MM 24h"},
        "open_24_7": {"type": "boolean", "description": "true if open all day every day"},
        "slot_minutes": {"type": "string", "description": "e.g. 60 for 1-hour slots"},
        "closed_days": {"type": "string", "description": "comma separated weekdays, or none"},
        "break": {"type": "string", "description": "'none' or leave out"},
        "bookings": {"type": "boolean"}, "orders": {"type": "boolean"}, "records": {"type": "boolean"},
        "booking_name": {"type": "string", "description": "what a booking is called, e.g. repair appointment"},
        "booking_asks": {"type": "string", "description": "what to collect from the caller, e.g. name, mobile and device problem"},
        "info": {"type": "string", "description": "facts callers may be told (address, delivery, payment), in English"},
        "steps": {"type": "string", "description": "how the agent must handle calls, in English, e.g. 'never quote a price; ask them to visit for inspection, then a quotation is given'"},
        "announce_ai": {"type": "boolean", "description": "say 'AI assistant' in the greeting"},
    }, lambda **a: _update(**a)),
    Tool("set_items", "Save the owner's list of services/items with prices.",
         {"items": {"type": "string", "description": "'name | price | unit | note; ...'"}}, _set_items, ["items"]),
    Tool("finish_setup", "Call when the essentials are set and the owner is happy. Then tell them to press 'Demo call'.",
         {}, lambda: {"done": True, "now": _summary()}),
]


def system(lang: str) -> str:
    return f"""You are Sahaaya's SETUP assistant, talking to a business OWNER (not a customer) who is setting up their
phone agent. Speak {NAMES.get(lang, 'English')} (the owner's language), warmly and briefly: max 2 sentences.
1. Understand their business and requirements. Save each answer IMMEDIATELY with update_settings / set_items.
2. Ask ONE short question at a time about what is still missing, only what matters:
   business type and name; hours (or 24/7); slot length; what the agent should collect from callers;
   services and prices, or how prices are handled (e.g. "visit the shop for inspection, then quotation");
   anything callers must be told (address etc.); a human name for the agent.
3. Save "steps" in the owner's words (how to handle calls, e.g. never quote prices; ask them to visit for checking,
   then a quotation is given). Never invent facts, prices or policies. When the essentials are set, give a 1-2 sentence summary, call finish_setup and tell
   them to press "Demo call" to test. If they ask for changes later, save them and confirm.
Note: the agent never claims to be human if a caller sincerely asks; "announce_ai" only controls the greeting.
Current settings: {_summary()}
{calendar_hint(2)}"""


def history() -> list:
    return db.get(KEY, [])


def reset():
    db.put(KEY, [])


def turn(text: str, lang: str) -> dict:
    if not history():
        _clean_start()
    msgs = history() + [{"role": "user", "content": text}]
    llm, by = LLM(), {t.name: t for t in TOOLS}
    done, changes = False, []
    for _ in range(6):
        m = llm.chat([{"role": "system", "content": system(lang)}] + msgs, tools=[t.schema() for t in TOOLS],
                     temperature=0.2, max_tokens=500)
        calls = m.get("tool_calls") or []
        if not calls:
            break
        msgs.append({"role": "assistant", "content": m.get("content") or "", "tool_calls": calls})
        for c in calls:
            t = by.get(c["function"]["name"])
            args = tool_args(c)
            res = t.fn(**{k: v for k, v in args.items() if k in t.params}) if t else {"error": "unknown"}
            done |= c["function"]["name"] == "finish_setup"
            if c["function"]["name"] != "finish_setup":
                changes.append({k: v for k, v in args.items()})
            msgs.append({"role": "tool", "tool_call_id": c["id"], "content": str(res)[:2500]})
    reply = (m.get("content") or "").strip() or "Saved."
    msgs.append({"role": "assistant", "content": reply})
    # keep the conversation short: drop old tool chatter, keep the words
    db.put(KEY, [x for x in msgs if x["role"] in ("user", "assistant") and x.get("content")][-24:])
    return {"reply": reply, "done": done, "changes": changes, "settings": service.settings()}
