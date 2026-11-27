"""Section 1: Service Center, for ANY small business (repair shop, kirana store, clinic, salon,
restaurant, or custom). The owner picks a template or simply describes the business in any language;
everything (hours, items and prices, what the agent can do) stays editable.
The agent can: answer from the owner's info and item list, book slots, take orders,
tell the status of the caller's orders/repairs, and raise tickets."""
import copy
import datetime
import json
import random
import re

from .. import db
from ..ai.agent import Tool
from .templates import TEMPLATES

DEFAULT_TYPE = "repair"


# ---------------- settings ----------------
def settings() -> dict:
    s = db.get("sc_settings")
    if not s:
        s = {"type": DEFAULT_TYPE, **copy.deepcopy(TEMPLATES[DEFAULT_TYPE])}
        s.pop("records", None)
        s["default_language"] = "kn"
    return s


def save_settings(new: dict):
    s = settings()
    for k, v in new.items():
        if k in ("words", "features") and isinstance(v, dict):
            s[k] = {**s.get(k, {}), **v}
        else:
            s[k] = v
    db.put("sc_settings", s)


def apply_template(kind: str, keep_name: bool = False):
    """Switch business type: new defaults, sample items and sample records (owner can edit all)."""
    t = copy.deepcopy(TEMPLATES.get(kind, TEMPLATES["custom"]))
    old = settings()
    sample = t.pop("records", [])
    if keep_name:
        t["name"], t["agent_name"] = old["name"], old["agent_name"]
    db.put("sc_settings", {"type": kind, "default_language": old.get("default_language", "kn"), **t})
    db.run("DELETE FROM records")
    db.run("DELETE FROM appointments")
    _seed_records(sample)
    _seed_bookings()


def _seed_records(rows):
    today = datetime.date.today()
    for rid, phone, name, title, detail, status, amount, days in rows:
        db.run("INSERT OR REPLACE INTO records(id,phone,name,title,detail,status,amount,due) VALUES(?,?,?,?,?,?,?,?)",
               (rid, phone, name, title, detail, status, amount, (today + datetime.timedelta(days=days)).isoformat()))


def _seed_bookings():
    if not settings()["features"].get("bookings"):
        return
    d = datetime.date.today() + datetime.timedelta(days=1)
    for hh in ("10:00", "11:30", "17:00"):
        if _t(settings()["open"]) <= _t(hh) < _t(settings()["close"]):
            db.run("INSERT INTO appointments(name,phone,purpose,start) VALUES(?,?,?,?)",
                   ("Walk-in", "9000000000", "Regular customer", f"{d.isoformat()} {hh}"))


def seed():
    if db.get("sc_settings") is None:
        apply_template(DEFAULT_TYPE)


# ---------------- setup by description (voice or text, any language) ----------------
def setup_from_description(text: str, lang: str = "en") -> dict:
    """The owner describes the business in their own words; the AI fills the settings.
    Nothing is invented: unknown fields keep the template's defaults."""
    from ..ai.languages import NAMES
    from ..ai.llm import LLM
    types = ", ".join(f"{k} ({v['label']})" for k, v in TEMPLATES.items())
    msg = LLM().chat([{"role": "system", "content":
        "A small business owner in India describes their business (any language, informal). Extract settings "
        "for their phone assistant. Use ONLY what they said; leave out anything not mentioned. JSON only:\n"
        "{\"type\": one of [" + types + "], \"name\": str, \"open\": \"HH:MM\" 24h, \"close\": \"HH:MM\", "
        "\"closed_days\": [weekday names in English], \"catalog\": [[item name, price number, unit, note]] with EVERY "
        "item or service they mentioned (count them; do not skip any), item name written as 'English name (name as they said it)' "
        "e.g. 'Rice (ಅಕ್ಕಿ)', unit in English e.g. '1 kg', '500 ml', 'plate', or 'service' for services, "
        "\"info\": \"other facts they said (delivery, address, payment, offers) in English\", "
        "\"features\": {\"bookings\": bool, \"orders\": bool}, "
        "\"readback\": \"2 short sentences in " + NAMES.get(lang, "English") + " confirming what you set up\"}"},
        {"role": "user", "content": text}], temperature=0.1, max_tokens=900)
    m = re.search(r"\{.*\}", msg.get("content") or "", re.S)
    try:
        data = json.loads(m.group(0))
    except Exception:
        return {"ok": False, "error": "Could not understand. Please describe your business again, simply."}
    # accuracy check: every price the owner said should appear in the item list; if not, ask once more
    said = {float(x) for x in re.findall(r"(?<![\d:])(\d{2,6})(?![\d:])", text.translate(_DIGITS))}
    got = {_num(r[1]) for r in data.get("catalog") or [] if len(r) > 1}
    missing = [x for x in said - got if x not in (7, 9, 24) and str(int(x)) not in str(data.get("info", ""))
               and str(int(x)) not in str(data.get("open", "")) + str(data.get("close", ""))]
    if data.get("catalog") is not None and missing:
        fix = LLM().chat([{"role": "system", "content": "You extracted an item list but missed items with these prices: "
                           f"{', '.join(f'{x:g}' for x in missing)}. Return the COMPLETE catalog JSON array only, same format."},
                          {"role": "user", "content": text}], temperature=0, max_tokens=600)
        m2 = re.search(r"\[.*\]", fix.get("content") or "", re.S)
        try:
            full = json.loads(m2.group(0))
            if isinstance(full, list) and len(full) > len(data["catalog"]):
                data["catalog"] = full
        except Exception:
            pass
    kind = data.get("type") if data.get("type") in TEMPLATES else "custom"
    apply_template(kind)
    upd = {k: data[k] for k in ("name", "open", "close", "closed_days", "info") if data.get(k)}
    for k in ("open", "close"):
        if k in upd and not re.fullmatch(r"\d{1,2}:\d{2}", str(upd[k])):
            upd.pop(k)
        elif k in upd:
            upd[k] = f"{int(upd[k].split(':')[0]):02d}:{upd[k].split(':')[1]}"
    if data.get("catalog"):
        upd["catalog"] = [[str(r[0]), _num(r[1]), str(r[2]) if len(r) > 2 else "", str(r[3]) if len(r) > 3 else ""]
                          for r in data["catalog"] if r]
    if isinstance(data.get("features"), dict):
        # a description can switch features ON (e.g. "we also take orders"); silence never switches the
        # business type's defaults off. Owners turn things off in Settings.
        on = {k: True for k, v in data["features"].items() if k in ("bookings", "orders") and v is True}
        if on:
            upd["features"] = on
    save_settings(upd)
    return {"ok": True, "type": kind, "label": TEMPLATES[kind]["label"], "settings": settings(),
            "readback": data.get("readback", "")}


_DIGITS = {ord(c): str(i % 10) for st in (0x0966, 0x09E6, 0x0A66, 0x0AE6, 0x0B66, 0x0BE6, 0x0C66, 0x0CE6, 0x0D66)
           for i, c in enumerate(chr(st + k) for k in range(10))}


def _num(v):
    try:
        return float(str(v).replace(",", "").replace("₹", "").strip())
    except ValueError:
        return 0


# ---------------- schedule ----------------
def _t(s):
    return datetime.datetime.strptime(s, "%H:%M").time()


def free_slots(date: str) -> dict:
    """ALL free slots of one day (the screen shows a few; the agent offers at most 3)."""
    cfg = settings()
    try:
        d = datetime.date.fromisoformat(date)
    except ValueError:
        return {"error": "date must be YYYY-MM-DD (use the calendar)"}
    if d < datetime.date.today():
        return {"date": date, "free": [], "note": "That date is in the past."}
    if d.strftime("%A") in cfg["closed_days"]:
        return {"date": date, "weekday": d.strftime("%A"), "free": [], "note": "Closed that day."}
    booked = {r["start"][11:16] for r in db.q(
        "SELECT start FROM appointments WHERE status='booked' AND start LIKE ?", (date + "%",))}
    step = datetime.timedelta(minutes=int(cfg["slot_minutes"]))
    cur = datetime.datetime.combine(d, _t(cfg["open"]))
    end = datetime.datetime.combine(d, _t(cfg["close"]))
    b0, b1 = (datetime.datetime.combine(d, _t(x)) for x in cfg["break"])
    now = datetime.datetime.now()
    free = []
    while cur + step <= end:
        if not (b0 <= cur < b1) and cur > now + datetime.timedelta(minutes=30) and cur.strftime("%H:%M") not in booked:
            free.append(f"{cur:%H:%M}-{cur + step:%H:%M}")
        cur += step
    return {"date": date, "weekday": d.strftime("%A"), "free": free}


def slots_to_offer(date: str, part_of_day: str = "", time: str = "") -> dict:
    """For the agent: if the caller named a time, say if it is free (or the nearest free times);
    otherwise at most 3 options spread over the day / part of day. Reading 8 slots aloud isn't human."""
    r = free_slots(date)
    allfree = r.get("free", [])
    if time and re.fullmatch(r"\d{1,2}:\d{2}", time.strip()):
        t = time.strip().zfill(5)
        if any(x.startswith(t) for x in allfree):
            return {**r, "free": [next(x for x in allfree if x.startswith(t))], "requested_time_free": True}
        mins = lambda x: int(x[:2]) * 60 + int(x[3:5])
        near = sorted(allfree, key=lambda x: abs(mins(x) - mins(t)))[:3]
        return {**r, "free": sorted(near), "requested_time_free": False,
                "note": "Requested time is not free; offer these nearest times."}
    free = allfree
    ranges = {"morning": ("00:00", "12:00"), "afternoon": ("12:00", "16:00"), "evening": ("16:00", "23:59")}
    if part_of_day in ranges:
        lo, hi = ranges[part_of_day]
        inside = [x for x in free if lo <= x[:5] < hi]
        if inside or not free:
            free = inside
        else:
            r["note"] = f"No {part_of_day} slots free that day; these are other times."
    if len(free) > 3:
        free = [free[0], free[len(free) // 2], free[-1]]
    return {**r, "free": free, "more_free_slots": max(0, len(allfree) - len(free)),
            "say": "These are only 3 examples of many free times. If the caller wants a different time, check that exact time."}


def book_slot(name: str, purpose: str, date: str, time: str, phone: str) -> dict:
    time = time.strip()[:5].zfill(5)
    slots = free_slots(date)
    if "error" in slots:
        return slots
    if not any(s.startswith(time) for s in slots["free"]):
        return {"booked": False, "reason": "That time is not free.", "free": slots_to_offer(date, time=time)["free"]}
    aid = db.run("INSERT INTO appointments(name,phone,purpose,start) VALUES(?,?,?,?)",
                 (name, phone, purpose, f"{date} {time}"))
    d = datetime.date.fromisoformat(date)
    end = datetime.datetime.combine(d, _t(time)) + datetime.timedelta(minutes=int(settings()["slot_minutes"]))
    db.notify("service", f"New {settings()['words']['booking']}: {name} ({purpose}) on {d:%d %b} at {time}")
    return {"booked": True, "booking_id": f"B{aid}", "when": f"{d:%A %d %B}, {time} to {end:%H:%M}",
            "sms": "confirmation SMS sent to caller"}


def my_bookings(phone: str) -> dict:
    rows = db.q("SELECT id,purpose,start FROM appointments WHERE phone=? AND status='booked' AND start>=? ORDER BY start",
                (phone, datetime.date.today().isoformat()))
    return {"bookings": [{"booking_id": f"B{r['id']}", "purpose": r["purpose"], "start": r["start"]} for r in rows]}


def cancel_booking(booking_id: str, phone: str) -> dict:
    bid = booking_id.upper().lstrip("B")
    r = db.q("SELECT * FROM appointments WHERE id=? AND phone=?", (bid, phone), one=True)
    if not r:
        return {"cancelled": False, "reason": "No such booking for this caller."}
    db.run("UPDATE appointments SET status='cancelled' WHERE id=?", (bid,))
    db.notify("service", f"Booking B{bid} cancelled by caller")
    return {"cancelled": True}


# ---------------- items, orders, records ----------------
def search_catalog(query: str = "") -> dict:
    """Owner's own item/service list with prices and stock. Matches any word of the query."""
    cat = settings().get("catalog", [])
    words = [w for w in re.findall(r"\w+", query.lower()) if len(w) > 2]
    hits = [r for r in cat if not words or any(w in r[0].lower() for w in words)]
    fmt = lambda r: {"item": r[0], "price_rupees": r[1], "unit": r[2], "note": r[3]}
    if not hits:
        return {"found": 0, "note": "Not in the list. Do not guess a price; say you will check with the owner.",
                "available_items": [r[0] for r in cat][:15]}
    return {"found": len(hits), "items": [fmt(r) for r in hits[:8]]}


def _match_item(name: str):
    cat = settings().get("catalog", [])
    n = name.lower().strip()
    exact = [r for r in cat if n == r[0].lower() or n in re.findall(r"[^()]+", r[0].lower().strip())]
    if exact:
        return exact[0]
    words = [w for w in re.findall(r"\w+", n) if len(w) > 2]
    hits = [r for r in cat if words and all(w in r[0].lower() for w in words)] or \
           [r for r in cat if words and any(w in r[0].lower() for w in words)]
    return hits[0] if len(hits) == 1 else None


def price_order(items: str) -> dict:
    """Exact total computed by the system (never by the AI). items: 'Rice x2; Milk x3'."""
    lines, total, problems = [], 0.0, []
    for part in re.split(r"[;\n]+", items):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"(.+?)\s*(?:[x×*]|qty)\s*([\d.]+)\s*$", part, re.I) or re.match(r"([\d.]+)\s*[x×*]?\s*(.+)$", part)
        if m and m.re.pattern.startswith("([\\d"):
            qty, name = float(m.group(1)), m.group(2)
        elif m:
            name, qty = m.group(1), float(m.group(2))
        else:
            name, qty = part, 1.0
        r = _match_item(name)
        if not r:
            problems.append(f"'{name.strip()}' is not in the list")
            continue
        if "out of stock" in str(r[3]).lower():
            problems.append(f"{r[0]} is out of stock")
            continue
        cost = qty * float(r[1])
        total += cost
        lines.append({"item": r[0], "qty": qty, "unit": r[2], "each_rupees": r[1], "cost_rupees": round(cost, 2)})
    out = {"lines": lines, "total_rupees": round(total, 2), "problems": problems}
    rules = settings().get("info", "")
    m = re.search(r"free\s*(?:delivery\s*)?(?:above|over|for orders above|more than)\s*(?:rs\.?|₹)?\s*(\d+)", rules, re.I)
    if m:
        limit = float(m.group(1))
        out["delivery"] = ("free (total is above " + f"{limit:g})") if total > limit else \
            (f"NOT free: total {total:g} is below the free-delivery amount {limit:g}. Tell the caller; "
             "if the delivery charge is not in the business info, say the owner will confirm it.")
    return out


def place_order(items: str, fulfilment: str, total_rupees: str = "", address: str = "", name: str = "",
                phone: str = "") -> dict:
    oid = f"O{random.randint(3000, 9999)}"
    fulfilment = "Home delivery" if "deliver" in fulfilment.lower() else "Pickup"
    detail = fulfilment + (f" to {address}" if address and fulfilment == "Home delivery" else "")
    db.run("INSERT INTO records(id,phone,name,title,detail,status,amount,due) VALUES(?,?,?,?,?,?,?,?)",
           (oid, phone, name or "Caller", items, detail, "New order", _num(total_rupees),
            datetime.date.today().isoformat()))
    db.notify("service", f"New order {oid}: {items} ({detail})")
    return {"order_id": oid, "status": "placed", "sms": "order details sent to caller by SMS"}


def my_records(phone: str, record_id: str = "") -> dict:
    rows = db.q("SELECT * FROM records WHERE phone=?" + (" AND id=?" if record_id else ""),
                (phone, record_id.upper()) if record_id else (phone,))
    if not rows and record_id:
        return {"found": 0, "note": "Nothing with that ID under this caller's number."}
    today = datetime.date.today()
    out = []
    for r in rows:
        d = datetime.date.fromisoformat(r["due"])
        out.append({"id": r["id"], "what": r["title"], "detail": r["detail"], "status": r["status"],
                    "amount_rupees": r["amount"],
                    "date": "today" if d == today else f"{d:%A %d %B}" + (" (already passed)" if d < today else "")})
    return {"found": len(out), "records": out}


def create_ticket(issue: str, details: str, phone: str, urgent: bool = False, section="service") -> dict:
    tid = f"T{random.randint(1000, 9999)}"
    db.run("INSERT INTO tickets(id,section,phone,issue,details,urgent) VALUES(?,?,?,?,?,?)",
           (tid, section, phone, issue, details, int(bool(urgent))))
    db.notify(section, f"{'URGENT ' if urgent else ''}Ticket {tid}: {issue}")
    return {"ticket_id": tid, "status": "created", "staff_callback": "within 2 hours" if urgent else "today"}


# ---------------- agent wiring ----------------
def tools(phone: str) -> list[Tool]:
    S = {"type": "string"}
    c = settings()
    w, f = c["words"], c["features"]
    out = [Tool("search_catalog", "Look up items/services in the owner's list: price, unit, stock. Use for any price question.",
                {"query": {**S, "description": "item or service name, in English if possible"}}, search_catalog)]
    if f.get("bookings"):
        out += [
            Tool("check_free_slots", f"Free {w['booking']} times for one date (YYYY-MM-DD from the calendar). "
                 "If the caller named a time, pass it as time (24h HH:MM, e.g. 5 in the evening = 17:00); "
                 "else optional part_of_day: morning, afternoon or evening.",
                 {"date": {**S, "description": "YYYY-MM-DD"}, "part_of_day": S, "time": {**S, "description": "HH:MM 24h"}},
                 slots_to_offer, ["date"]),
            Tool("book_slot", f"Book a {w['booking']} after the caller confirmed name, {w['purpose']}, date and time.",
                 {"name": S, "purpose": {**S, "description": w["purpose"]}, "date": {**S, "description": "YYYY-MM-DD"},
                  "time": {**S, "description": "start time HH:MM from the free slots"}},
                 lambda **a: book_slot(phone=phone, **a), ["name", "purpose", "date", "time"]),
            Tool("my_bookings", "The caller's upcoming bookings.", {}, lambda: my_bookings(phone)),
            Tool("cancel_booking", "Cancel one of the caller's bookings after they confirm.",
                 {"booking_id": S}, lambda booking_id: cancel_booking(booking_id, phone), ["booking_id"]),
        ]
    if f.get("orders"):
        out.append(Tool("price_order", "Exact total and delivery check for an order. ALWAYS use it before reading back a total; "
                        "never add up prices yourself.",
                        {"items": {**S, "description": "items with quantities, e.g. 'Rice x2; Milk x2'"}}, price_order, ["items"]))
        out.append(Tool("place_order", "Place the caller's order ONLY after reading back every item, the total and "
                        "pickup/delivery, and the caller said yes.",
                        {"items": {**S, "description": "items with quantities"}, "fulfilment": {**S, "description": "pickup or delivery"},
                         "total_rupees": S, "address": S, "name": S},
                        lambda **a: place_order(phone=phone, **a), ["items", "fulfilment"]))
    if f.get("records", True):
        out.append(Tool("my_status", f"Status of the caller's {w['record']}s (optionally one ID).",
                        {"record_id": S}, lambda record_id="": my_records(phone, record_id)))
    out.append(Tool("create_ticket", "Register a complaint or staff callback.",
                    {"issue": S, "details": S, "urgent": {"type": "boolean"}},
                    lambda issue, details="", urgent=False: create_ticket(issue, details, phone, urgent), ["issue"]))
    return out


def _12h(hhmm: str) -> str:
    return datetime.datetime.strptime(hhmm, "%H:%M").strftime("%I:%M %p").lstrip("0").replace(":00 ", " ")


def turn_rules() -> str:
    f = settings()["features"]
    rules = ["- Prices and stock: always use search_catalog, never guess."]
    if f.get("bookings"):
        rules.append("- If the caller wants to come in, book, or asks about a day or time: call check_free_slots FIRST, "
                     "then offer the options it returns. The options are only examples: when the caller names a time (e.g. 'evening 5' = 17:00), "
                     "ALWAYS call check_free_slots again with that time. Never say a time is not free unless that call said so.")
    if f.get("orders"):
        rules.append("- Orders: call price_order for the exact total and delivery check (never add prices yourself), "
                     "read back items + total + pickup/delivery, place_order only after yes.")
    rules.append("- Questions about their existing order/booking/repair: check with the tools first.")
    return "\n".join(rules)


def persona() -> str:
    c = settings()
    w, f = c["words"], c["features"]
    can = [x for x, on in (("answer questions and prices", True), (f"book {w['booking']}s", f.get("bookings")),
                           ("take orders", f.get("orders")), (f"tell the status of {w['record']}s", f.get("records", True)))
           if on]
    known = ""
    if f.get("bookings"):
        today = datetime.date.today()
        parts = []
        for i, word in ((0, "today"), (1, "tomorrow")):
            d = (today + datetime.timedelta(days=i)).isoformat()
            o = slots_to_offer(d)
            parts.append(f"{word} {d}: " + (", ".join(o["free"]) if o["free"] else o.get("note", "none free")))
        known = ("\nFREE TIMES ALREADY CHECKED (offer these right away; for any other day or a specific time, "
                 "call check_free_slots): " + " | ".join(parts))
    cat = "; ".join(f"{r[0]}: {r[1]:g} rupees/{r[2]}" + (f" ({r[3]})" if r[3] else "") for r in c.get("catalog", [])[:25])
    return f"""You are {c['agent_name']}, the phone assistant of "{c['name']}" ({TEMPLATES.get(c['type'], TEMPLATES['custom'])['label']}).
You can: {', '.join(can)}. Anything else: offer a staff callback.
How to help: {c.get('steps', '')}
Hours: {_12h(c['open'])} to {_12h(c['close'])}{', closed ' + ', '.join(c['closed_days']) if c['closed_days'] else ', open all days'}; break {_12h(c['break'][0])} to {_12h(c['break'][1])}.
BUSINESS INFO: {c['info']}
ITEMS AND PRICES (owner's list): {cat or 'none listed'}{known}"""
