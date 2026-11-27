"""Section 1: Service Center (e.g. a phone/electronics repair shop).
The agent asks the issue, checks the owner's schedule, books a free slot and tracks repairs."""
import datetime
import random

from .. import db
from ..ai.agent import Tool

DEFAULT = {
    "name": "Mysuru Mobile Care",
    "agent_name": "Priya",
    "default_language": "kn",
    "languages": ["kn", "hi", "en", "te", "ta"],
    "open": "10:00", "close": "20:00", "slot_minutes": 30,
    "closed_days": ["Sunday"],
    "break": ["13:30", "14:30"],
    "info": ("Phone, laptop and tablet repairs. Screen replacement from 1,500 rupees (about 1 hour). "
             "Battery replacement 1,200 rupees (30 minutes). Charging port repair 800 rupees. "
             "Water damage check is free, repair price after inspection. 3 months warranty on parts. "
             "Address: 12, Sayyaji Rao Road, Mysuru, near Clock Tower."),
}


def settings() -> dict:
    return {**DEFAULT, **(db.get("sc_settings") or {})}


def save_settings(new: dict):
    db.put("sc_settings", {**settings(), **new})


def seed():
    if db.q("SELECT COUNT(*) n FROM jobs", one=True)["n"]:
        return
    today = datetime.date.today()
    jobs = [("J1001", "9876543210", "Ravi", "Samsung Galaxy S23", "Screen broken", "Ready for pickup", 1500, today),
            ("J1002", "9123456780", "Lakshmi", "iPhone 13", "Battery drains fast", "In repair", 1200,
             today + datetime.timedelta(days=1)),
            ("J1003", "9988776655", "Arun", "Dell laptop", "Not charging", "Waiting for spare part", 800,
             today + datetime.timedelta(days=3))]
    for j in jobs:
        db.run("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?)", (*j[:7], j[7].isoformat()))
    # a few existing bookings so the schedule is realistic
    tmr = today + datetime.timedelta(days=1)
    for hh in ("10:00", "10:30", "11:30", "16:00"):
        db.run("INSERT INTO appointments(name,phone,device,issue,start) VALUES(?,?,?,?,?)",
               ("Walk-in", "9000000000", "Phone", "Check-up", f"{tmr.isoformat()} {hh}"))


def _t(s):
    return datetime.datetime.strptime(s, "%H:%M").time()


def free_slots(date: str) -> dict:
    date_str = date
    cfg = settings()
    try:
        d = datetime.date.fromisoformat(date_str)
    except ValueError:
        return {"error": "date must be YYYY-MM-DD (use the calendar)"}
    if d < datetime.date.today():
        return {"date": date_str, "free": [], "note": "That date is in the past."}
    if d.strftime("%A") in cfg["closed_days"]:
        return {"date": date_str, "weekday": d.strftime("%A"), "free": [], "note": "Shop is closed that day."}
    booked = {r["start"][11:16] for r in db.q(
        "SELECT start FROM appointments WHERE status='booked' AND start LIKE ?", (date_str + "%",))}
    step = datetime.timedelta(minutes=int(cfg["slot_minutes"]))
    cur = datetime.datetime.combine(d, _t(cfg["open"]))
    end = datetime.datetime.combine(d, _t(cfg["close"]))
    b0, b1 = (datetime.datetime.combine(d, _t(x)) for x in cfg["break"])
    now = datetime.datetime.now()
    free = []
    while cur + step <= end:
        if not (b0 <= cur < b1) and cur > now + datetime.timedelta(minutes=30) \
                and cur.strftime("%H:%M") not in booked:
            free.append(f"{cur:%H:%M}-{cur + step:%H:%M}")
        cur += step
    return {"date": date_str, "weekday": d.strftime("%A"), "free": free[:8],
            "more_free_slots": max(0, len(free) - 8)}


def book_slot(name: str, device: str, issue: str, date: str, time: str, phone: str) -> dict:
    time = time[:5]
    slots = free_slots(date)
    if "error" in slots:
        return slots
    if not any(s.startswith(time) for s in slots["free"]) and time not in str(slots):
        return {"booked": False, "reason": "That slot is not free.", "free": slots["free"]}
    aid = db.run("INSERT INTO appointments(name,phone,device,issue,start) VALUES(?,?,?,?,?)",
                 (name, phone, device, issue, f"{date} {time}"))
    d = datetime.date.fromisoformat(date)
    end = (datetime.datetime.combine(d, _t(time)) + datetime.timedelta(minutes=int(settings()["slot_minutes"])))
    db.notify("service", f"New booking: {name}, {device} ({issue}) on {d:%d %b} at {time}")
    return {"booked": True, "booking_id": f"B{aid}", "when": f"{d:%A %d %B}, {time} to {end:%H:%M}",
            "sms": "confirmation SMS sent to caller"}


def my_bookings(phone: str) -> dict:
    rows = db.q("SELECT id,device,issue,start,status FROM appointments WHERE phone=? AND status='booked' "
                "AND start>=? ORDER BY start", (phone, datetime.date.today().isoformat()))
    return {"bookings": [{"booking_id": f"B{r['id']}", **{k: r[k] for k in ('device', 'issue', 'start')}} for r in rows]}


def cancel_booking(booking_id: str, phone: str) -> dict:
    bid = booking_id.upper().lstrip("B")
    r = db.q("SELECT * FROM appointments WHERE id=? AND phone=?", (bid, phone), one=True)
    if not r:
        return {"cancelled": False, "reason": "No such booking for this caller."}
    db.run("UPDATE appointments SET status='cancelled' WHERE id=?", (bid,))
    db.notify("service", f"Booking B{bid} cancelled by caller")
    return {"cancelled": True}


def repair_status(phone: str, job_id: str = "") -> dict:
    rows = db.q("SELECT * FROM jobs WHERE phone=?" + (" AND id=?" if job_id else ""),
                (phone, job_id.upper()) if job_id else (phone,))
    if not rows and job_id:
        return {"found": 0, "note": "No repair with that job ID under this caller's number."}
    today = datetime.date.today()
    out = []
    for r in rows:
        d = datetime.date.fromisoformat(r["ready_by"])
        out.append({"job_id": r["id"], "device": r["device"], "issue": r["issue"], "status": r["status"],
                    "amount_rupees": r["amount"],
                    "ready_by": "today" if d == today else f"{d:%A %d %B}" + (" (already passed)" if d < today else "")})
    return {"found": len(out), "repairs": out}


def create_ticket(issue: str, details: str, phone: str, urgent: bool = False, section="service") -> dict:
    tid = f"T{random.randint(1000, 9999)}"
    db.run("INSERT INTO tickets(id,section,phone,issue,details,urgent) VALUES(?,?,?,?,?,?)",
           (tid, section, phone, issue, details, int(bool(urgent))))
    db.notify(section, f"{'URGENT ' if urgent else ''}Ticket {tid}: {issue}")
    return {"ticket_id": tid, "status": "created", "staff_callback": "within 2 hours" if urgent else "today"}


def slots_to_offer(date: str, part_of_day: str = "") -> dict:
    """For the phone agent: max 3 options spread over the day (or within morning/afternoon/evening),
    because reading 8 slots aloud is not how a human talks."""
    r = free_slots(date)
    free = r.get("free", [])
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
    return {**r, "free": free, "more_free_slots": max(0, len(r.get("free", [])) - len(free)),
            "say": "Offer these options naturally; mention more are available if they want another time."}


def tools(phone: str) -> list[Tool]:
    S = {"type": "string"}
    return [
        Tool("check_free_slots", "Free appointment slots for one date (YYYY-MM-DD from the calendar). "
             "Optional part_of_day: morning, afternoon or evening if the caller said one.",
             {"date": {**S, "description": "YYYY-MM-DD"}, "part_of_day": S}, slots_to_offer, ["date"]),
        Tool("book_slot", "Book a repair appointment. Only after the caller confirmed name, device, issue, date and time.",
             {"name": S, "device": S, "issue": S, "date": {**S, "description": "YYYY-MM-DD"},
              "time": {**S, "description": "start time HH:MM, one of the free slots"}},
             lambda **a: book_slot(phone=phone, **a), ["name", "device", "issue", "date", "time"]),
        Tool("my_bookings", "The caller's upcoming appointments.", {}, lambda: my_bookings(phone)),
        Tool("cancel_booking", "Cancel one of the caller's bookings after they confirm.",
             {"booking_id": S}, lambda booking_id: cancel_booking(booking_id, phone), ["booking_id"]),
        Tool("repair_status", "Status of the caller's device repairs (optionally one job ID like J1001).",
             {"job_id": S}, lambda job_id="": repair_status(phone, job_id)),
        Tool("create_ticket", "Register a complaint or staff callback.",
             {"issue": S, "details": S, "urgent": {"type": "boolean"}},
             lambda issue, details="", urgent=False: create_ticket(issue, details, phone, urgent), ["issue"]),
    ]


def _12h(hhmm: str) -> str:
    t = datetime.datetime.strptime(hhmm, "%H:%M")
    return t.strftime("%I:%M %p").lstrip("0").replace(":00 ", " ")


def turn_rules() -> str:
    return ("- If the caller wants to come in, book, or asks about a day or time: call check_free_slots FIRST, "
            "then offer the options it returns.\n- Repair or booking questions: check with the tools before answering.")


def persona() -> str:
    c = settings()
    return f"""You are {c['agent_name']}, the receptionist of "{c['name']}", a repair service centre.
Your job on calls:
1. Ask what device it is and what the problem is (if not said).
2. Tell the price or time from the business info if known.
3. Offer an appointment. As soon as the caller wants to come in or asks about a day/time, FIRST call
   check_free_slots (never ask "what time suits you" before checking), then offer the options,
   ask their name, read back device, issue, day and time, and book only after they say yes.
4. Tell the booking day and time range clearly. Repair status questions: use repair_status.
Shop hours: {_12h(c['open'])} to {_12h(c['close'])}, closed {', '.join(c['closed_days'])}, lunch break {_12h(c['break'][0])} to {_12h(c['break'][1])}.
BUSINESS INFO: {c['info']}"""
