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


def discover(base_url: str, api_key: str, key_header: str = "X-API-Key", name: str = "") -> dict:
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
    new = [{"id": len(rules()) + i + 1, "rule": r, "said": instruction, "lang": lang, "approved": False}
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


def call_op(conn: dict, op: dict, args: dict, guard: Guard) -> dict:
    if op["permission"] == "blocked":
        return {"error": "This action is blocked by the business owner."}
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
    base = ["Re-check / re-verify only helps when the documents are fine. If a document is blurry, "
            "missing or not uploaded, the fix is the upload link, never a re-check."]
    return "\n".join("- " + r for r in approved + base)


def persona() -> str:
    conn = connection()
    approved = [r["rule"] for r in rules() if r["approved"]]
    name = conn["name"] if conn else "the company"
    return f"""You are the customer support voice agent of "{name}". {conn.get('description', '') if conn else ''}
You work inside the company's dashboard using the tools. Start by finding the caller's account
with their phone number. Explain problems simply, like a helpful human, and guide the caller
step by step when they must do something themselves.
Before offering an action, make sure the record shows it can actually help. For example, a re-check
cannot fix a blurry or missing document: then the customer must re-upload, so offer the upload link.
An "expected" date on an order that is on hold is NOT a promise: never promise dates; follow the owner's rules.
Dates from the dashboard are YYYY-MM-DD; use the calendar to say the weekday correctly.
OWNER'S RULES (follow exactly):
{chr(10).join('- ' + r for r in approved) or '- (none yet)'}"""
