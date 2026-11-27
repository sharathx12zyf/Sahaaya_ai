"""Section 2: Dashboard Connect.
1. Connect: the business gives its dashboard's base URL + API key. We read its OpenAPI
   description and turn every action into an agent tool automatically.
2. Permissions: read actions allowed, changing actions need caller confirmation, deleting is blocked
   (owner can change each one).
3. Teach: the owner explains in ANY language how to handle cases; the AI turns it into rules.
4. Safety (enforced in code, not just the prompt): only the caller's own records are shown, and
   changing actions only run on records that belong to the caller."""
import json
import re

import requests

from .. import db
from ..ai.agent import Tool
from ..ai.llm import LLM

DEFAULT_PERMISSION = {"get": "allowed", "post": "confirm", "put": "confirm", "patch": "confirm", "delete": "blocked"}
ID_FIELDS = re.compile(r"(^|_)(id|user_id|order_id|account|customer_id)$")


def connection() -> dict | None:
    return db.get("connection")


def _sheet_csv_url(url: str) -> str | None:
    m = re.search(r"docs\.google\.com/spreadsheets/d/([\w-]+)", url)
    if m:
        gid = re.search(r"[#&?]gid=(\d+)", url)
        return f"https://docs.google.com/spreadsheets/d/{m.group(1)}/export?format=csv" + (f"&gid={gid.group(1)}" if gid else "")
    if url.lower().split("?")[0].endswith(".csv"):
        return url
    return None


def _read_csv(url: str, conn: dict | None = None) -> list[dict]:
    import csv
    import io
    h = {conn["key_header"]: conn["api_key"]} if conn and conn.get("api_key") else {}
    r = requests.get(url, timeout=10, headers=h)
    r.raise_for_status()
    return list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))))


def discover_sheet(url: str, api_key: str = "", key_header: str = "X-API-Key", name: str = "") -> dict:
    """For companies without an API: a Google Sheet (shared 'anyone with link') or any CSV link."""
    csv_url = _sheet_csv_url(url)
    try:
        rows = _read_csv(csv_url, {"api_key": api_key, "key_header": key_header})
    except Exception as e:
        return {"ok": False, "error": f"Could not read the sheet ({e.__class__.__name__}). Share it as 'anyone with the link'."}
    if not rows:
        return {"ok": False, "error": "The sheet is empty."}
    cols = list(rows[0].keys())
    phone_col = next((c for c in cols if re.search(r"phone|mobile|contact", c, re.I)), None)
    ops = [{"id": "search_records", "method": "SHEET", "path": csv_url, "params": {"query": "string"},
            "summary": f"Search the sheet (columns: {', '.join(cols)[:200]})", "permission": "allowed"}]
    if phone_col:
        ops.insert(0, {"id": "find_my_records", "method": "SHEET", "path": csv_url, "params": {"phone": "string"},
                       "summary": f"Find the caller's rows by phone number (column '{phone_col}')", "permission": "allowed"})
    conn = {"name": name or "Company sheet", "description": "", "base_url": url, "api_key": api_key,
            "key_header": key_header, "ops": ops, "kind": "sheet", "phone_col": phone_col}
    db.put("connection", conn)
    return {"ok": True, "name": conn["name"], "actions": len(ops)}


def _drop_sample_rules(new_url: str):
    """Switching to a different dashboard: the demo company's sample rules no longer apply.
    Rules the owner taught are kept."""
    old = connection()
    if old and old.get("base_url") != new_url:
        db.put("rules", [r for r in rules() if not r.get("said", "").startswith("(sample rules")])


def discover(base_url: str, api_key: str, key_header: str = "X-API-Key", name: str = "") -> dict:
    _drop_sample_rules(base_url)
    if _sheet_csv_url(base_url):
        return discover_sheet(base_url, api_key, key_header, name)
    base = base_url.rstrip("/")
    spec = None
    for path in ("/openapi.json", "/swagger.json", "/api/openapi.json"):
        try:
            r = requests.get(base + path, timeout=10, headers={key_header: api_key})
            if r.ok and "paths" in r.json():
                spec = r.json()
                break
        except Exception:
            continue
    if not spec:
        return {"ok": False, "error": "Could not find an API description (openapi.json) at that address."}
    ops = []
    for path, methods in spec["paths"].items():
        for m, op in methods.items():
            if m not in DEFAULT_PERMISSION:
                continue
            oid = re.sub(r"\W+", "_", op.get("operationId") or f"{m}_{path}").strip("_")[:60]
            params = {p["name"]: p.get("schema", {}).get("type", "string")
                      for p in op.get("parameters", []) if p.get("in") in ("path", "query")}
            ops.append({"id": oid, "method": m.upper(), "path": path,
                        "summary": op.get("summary") or op.get("description") or oid,
                        "params": params, "permission": DEFAULT_PERMISSION[m]})
    title = re.sub(r"\s*\b(admin|api|dashboard)\b", "", spec.get("info", {}).get("title", ""), flags=re.I).strip()
    conn = {"name": name or title or "Company",
            "description": spec.get("info", {}).get("description", ""),
            "base_url": base, "api_key": api_key, "key_header": key_header, "ops": ops}
    db.put("connection", conn)
    return {"ok": True, "name": conn["name"], "actions": len(ops)}


def set_permission(op_id: str, permission: str):
    conn = connection()
    for o in conn["ops"]:
        if o["id"] == op_id and permission in ("allowed", "confirm", "blocked"):
            o["permission"] = permission
    db.put("connection", conn)


# ---------- company profile ----------
def profile() -> dict:
    conn = connection() or {}
    p = db.get("connect_profile") or {}
    return {"name": p.get("name") or conn.get("name") or "Company", "about": p.get("about") or conn.get("description", ""),
            "agent_name": p.get("agent_name") or "Sahaaya", "default_language": p.get("default_language", "kn")}


def save_profile(data: dict):
    db.put("connect_profile", {**profile(), **{k: v for k, v in data.items() if v}})


def describe_company(text: str, lang: str = "en") -> dict:
    """Owner describes the company and how support should work, in any language:
    fills the profile and proposes rules (owner approves them)."""
    from ..ai.languages import NAMES
    conn = connection()
    actions = "\n".join(f"- {o['id']}: {o['summary']}" for o in conn["ops"]) if conn else "(none connected yet)"
    msg = LLM().chat([{"role": "system", "content":
        "A company owner describes their company and how phone support should handle customers (any language). "
        "Use ONLY what they said. JSON only: {\"name\": str, \"about\": \"what the company does, in English\", "
        "\"agent_name\": str or null, \"rules\": [\"When ..., do ...\" only for instructions they gave, using these "
        "dashboard action names where relevant], \"readback\": \"2 short sentences in " + NAMES.get(lang, "English") +
        " confirming what you understood\"}\nDashboard actions:\n" + actions},
        {"role": "user", "content": text}], temperature=0.1, max_tokens=800)
    m = re.search(r"\{.*\}", msg.get("content") or "", re.S)
    try:
        data = json.loads(m.group(0))
    except Exception:
        return {"ok": False, "error": "Could not understand, please describe it again more simply."}
    save_profile({"name": data.get("name"), "about": data.get("about"), "agent_name": data.get("agent_name")})
    new = [{"id": max([r["id"] for r in rules()] + [0]) + i + 1, "rule": r, "said": text, "lang": lang, "approved": False}
           for i, r in enumerate(data.get("rules") or [])]
    db.put("rules", rules() + new)
    return {"ok": True, "profile": profile(), "rules": new, "readback": data.get("readback", "")}


def seed_demo_rules():
    """The sample QuickKart dashboard comes with the owner's KYC rules already taught (as an example)."""
    if rules():
        return
    demo = ["When a customer asks about KYC or an order on hold, check their account and orders first.",
            "If the documents are fine, offer to run recheck_kyc (after the customer says yes) to verify and release held orders.",
            "If a document is blurry, missing, not uploaded or KYC is not started, NEVER offer a re-check or verification: "
            "offer send_kyc_upload_link and explain the steps."]
    db.put("rules", [{"id": i + 1, "rule": r, "said": "(sample rules for the QuickKart demo)", "lang": "en", "approved": True}
                     for i, r in enumerate(demo)])


# ---------- teaching ----------
def rules() -> list[dict]:
    return db.get("rules", [])


def teach(instruction: str, lang: str = "en") -> dict:
    """Owner explains in any language -> clear English rules for the agent + a read-back in their language."""
    conn = connection()
    actions = "\n".join(f"- {o['id']}: {o['summary']}" for o in conn["ops"]) if conn else "(no dashboard connected)"
    from ..ai.languages import NAMES
    msg = LLM().chat([{"role": "system", "content":
        "You turn a business owner's spoken instructions (any Indian language, maybe informal) into precise "
        "rules for a customer-service phone agent. Write ONLY what the owner actually said, split into "
        "clear steps (usually 1 to 3 rules); never add rules, promises or actions the owner did not mention. Use the dashboard action names where relevant. "
        "Answer with JSON only: {\"rules\": [\"When ..., do ...\"], \"readback\": \"one or two sentences in "
        f"{NAMES.get(lang, 'English')} confirming what you understood\"}}\nDashboard actions:\n{actions}"},
        {"role": "user", "content": instruction}], temperature=0.1, max_tokens=600)
    m = re.search(r"\{.*\}", msg.get("content") or "", re.S)
    try:
        data = json.loads(m.group(0))
    except Exception:
        return {"ok": False, "error": "Could not understand, please say it again more simply."}
    new = [{"id": max([r["id"] for r in rules()] + [0]) + i + 1, "rule": r, "said": instruction, "lang": lang, "approved": False}
           for i, r in enumerate(data.get("rules", []))]
    db.put("rules", rules() + new)
    return {"ok": True, "rules": new, "readback": data.get("readback", "")}


def approve_rule(rule_id: int, approved: bool = True, delete: bool = False):
    rs = [r for r in rules() if not (delete and r["id"] == rule_id)]
    for r in rs:
        if r["id"] == rule_id:
            r["approved"] = approved
    db.put("rules", rs)


# ---------- calling the dashboard safely ----------
class Guard:
    """Per-call privacy state: which records this caller may see / change."""

    def __init__(self, caller: str):
        self.caller = re.sub(r"\D", "", caller)[-10:]
        self.allowed_ids: set[str] = set()
        self.withheld: dict[str, str] = {}      # record id -> its phone (for verification)

    def _phones(self, obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k.lower() in ("phone", "mobile", "phone_number") and v:
                    yield re.sub(r"\D", "", str(v))[-10:]
                elif isinstance(v, (dict, list)):
                    yield from self._phones(v)
        elif isinstance(obj, list):
            for x in obj:
                yield from self._phones(x)

    def _ids(self, obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if ID_FIELDS.search(k.lower()) and isinstance(v, (str, int)):
                    yield str(v).upper()
                elif isinstance(v, (dict, list)):
                    yield from self._ids(v)
        elif isinstance(obj, list):
            for x in obj:
                yield from self._ids(x)

    def filter(self, data, path_values):
        phones = set(self._phones(data))
        ids = set(self._ids(data)) | {str(v).upper() for v in path_values}
        if phones and self.caller not in phones and not (ids & self.allowed_ids):
            for i in ids:
                self.withheld[i] = next(iter(phones))
            return {"withheld": True, "note": "This record belongs to a different phone number. Do not reveal "
                    "anything about it. Ask the caller for the last 4 digits of the registered phone number "
                    "and call verify_caller."}
        if phones or not path_values or set(map(lambda v: str(v).upper(), path_values)) & self.allowed_ids:
            self.allowed_ids |= ids
        return data

    def verify(self, record_id: str, phone_last4: str) -> dict:
        last4 = phone_last4
        p = self.withheld.get(record_id.upper())
        if p and re.sub(r"\D", "", last4)[-4:] == p[-4:]:
            self.allowed_ids.add(record_id.upper())
            return {"verified": True}
        return {"verified": False, "note": "Does not match. Do not share any details."}


def _sheet_op(conn: dict, op: dict, args: dict, guard: "Guard") -> dict:
    try:
        rows = _read_csv(op["path"], conn)
    except Exception as e:
        return {"error": f"sheet not reachable ({e.__class__.__name__})"}
    pc = conn.get("phone_col")
    norm = lambda v: re.sub(r"\D", "", str(v))[-10:]
    if op["id"] == "find_my_records":
        mine = [r for r in rows if pc and norm(r.get(pc, "")) == guard.caller]
        return {"found": len(mine), "rows": mine[:10]}
    words = [w.lower() for w in re.findall(r"\w+", str(args.get("query", ""))) if len(w) > 1]
    hits = [r for r in rows if all(any(w in str(v).lower() for v in r.values()) for w in words)] if words else rows
    if pc:   # privacy: only the caller's own rows from a sheet that has phone numbers
        hidden = [r for r in hits if norm(r.get(pc, "")) != guard.caller]
        hits = [r for r in hits if norm(r.get(pc, "")) == guard.caller]
        if hidden and not hits:
            return {"found": 0, "withheld": True, "note": "Matching rows belong to other phone numbers. Reveal nothing."}
    return {"found": len(hits), "rows": hits[:10]}


def call_op(conn: dict, op: dict, args: dict, guard: Guard) -> dict:
    if op["permission"] == "blocked":
        return {"error": "This action is blocked by the business owner."}
    if op["method"] == "SHEET":
        return _sheet_op(conn, op, args, guard)
    path, path_values = op["path"], []
    for name in re.findall(r"\{(\w+)\}", path):
        val = str(args.get(name, "")).strip()
        if not val:
            return {"error": f"missing {name}"}
        path_values.append(val)
        path = path.replace("{" + name + "}", requests.utils.quote(val))
    if op["method"] != "GET":
        # changing actions only on records already shown to belong to this caller
        if not all(v.upper() in guard.allowed_ids for v in path_values):
            return {"error": "Not allowed: first look up the caller's own account (or verify them)."}
    query = {k: v for k, v in args.items() if k in op["params"] and "{" + k + "}" not in op["path"]}
    try:
        r = requests.request(op["method"], conn["base_url"] + path, params=query, timeout=10,
                             headers={conn["key_header"]: conn["api_key"]})
    except Exception as e:
        return {"error": f"dashboard not reachable ({e.__class__.__name__})"}
    try:
        data = r.json()
    except ValueError:
        data = r.text[:1500]
    if r.status_code == 404:
        return {"found": False, "detail": data}
    if r.status_code >= 400:
        return {"error": f"dashboard error {r.status_code}", "detail": data}
    if op["method"] == "GET":
        data = guard.filter(data, path_values)
    else:
        db.notify("connect", f"Agent ran {op['id']} for {', '.join(path_values)}")
    return {"result": data}


def tools(phone: str) -> tuple[list[Tool], Guard]:
    from ..service_center.core import create_ticket
    conn, guard = connection(), Guard(phone)
    out = []
    if conn:
        for op in conn["ops"]:
            if op["permission"] == "blocked":
                continue
            desc = f"[{op['method']}] {op['summary']}"
            if op["permission"] == "confirm":
                desc += ". CHANGES DATA: explain to the caller and act only after they say yes."
            params = {k: {"type": "string"} for k in op["params"]}
            out.append(Tool(op["id"], desc, params,
                            (lambda o: lambda **a: call_op(conn, o, a, guard))(op), list(op["params"])))
    out.append(Tool("verify_caller", "Verify a caller for a record using the last 4 digits of its registered phone.",
                    {"record_id": {"type": "string"}, "phone_last4": {"type": "string"}},
                    guard.verify, ["record_id", "phone_last4"]))
    out.append(Tool("create_ticket", "Register a complaint or staff callback.",
                    {"issue": {"type": "string"}, "details": {"type": "string"}, "urgent": {"type": "boolean"}},
                    lambda issue, details="", urgent=False: create_ticket(issue, details, phone, urgent, "connect"),
                    ["issue"]))
    return out, guard


def prefetch(caller: str, tools_by_name: dict) -> str:
    """Look up the caller's account as the call starts, so the first answer is faster."""
    conn = connection()
    for op in (conn or {}).get("ops", []):
        if op["method"] == "GET" and op["permission"] != "blocked" and \
                any("phone" in p.lower() for p in re.findall(r"\{(\w+)\}", op["path"]) + list(op["params"])):
            pname = next(p for p in op["params"] if "phone" in p.lower())
            res = tools_by_name[op["id"]].fn(**{pname: caller})
            return (f"Caller's account (already looked up with {op['id']}; do not look it up again): "
                    + json.dumps(res, ensure_ascii=False)[:1500])
    return ""


def turn_rules() -> str:
    approved = [r["rule"] for r in rules() if r["approved"]]
    base = ["Before offering an action, check the record shows it can actually fix the problem."]
    return "\n".join("- " + r for r in approved + base)


def persona() -> str:
    approved = [r["rule"] for r in rules() if r["approved"]]
    p = profile()
    return f"""You are {p['agent_name']}, the customer support voice agent of "{p['name']}". {p['about']}
You work inside the company's dashboard using the tools. Start by finding the caller's account
with their phone number. Explain problems simply, like a helpful human, and guide the caller
step by step when they must do something themselves.
Before offering an action, make sure the record shows it can actually help the problem.
An "expected" date on an order that is on hold is NOT a promise: never promise dates; follow the owner's rules.
Dates from the dashboard are YYYY-MM-DD; use the calendar to say the weekday correctly.
OWNER'S RULES (follow exactly):
{chr(10).join('- ' + r for r in approved) or '- (none yet)'}"""
