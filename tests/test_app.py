"""Offline tests: no API keys or internet needed."""
import datetime
from conftest import FakeLLM, tool_call
from app import db
from app.ai.agent import Agent
from app.ai.languages import detect_script_language, foreign_script
from app.connect import core as connect
from app.service_center import core as service

db.init(); service.seed()


def test_starts_without_keys(monkeypatch):
    monkeypatch.delenv("SARVAM_API_KEY", raising=False); monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        assert c.get("/").status_code == 200
        assert c.get("/api/status").json()["keys"] == {"sarvam": False, "nvidia": False}
        r = c.post("/api/call/start", data={"section": "service", "caller": "9000011111"}).json()
        assert r["key_not_set"] and "not set" in r["error"]
        assert c.get("/api/service/overview").status_code == 200   # dashboard still works


def test_language_detection():
    assert detect_script_language("ನಾಳೆ ಬರಬಹುದಾ?") == "kn"
    assert detect_script_language("कल आ सकते हैं?") == "hi"
    assert detect_script_language("రేపు రావచ్చా?") == "te"
    assert detect_script_language("நாளை வரலாமா?") == "ta"
    assert foreign_script("staff 24 hours ಒಳಗೆ call பண்ணுவாங்க", "ta")


def _next_open_day():
    d = datetime.date.today() + datetime.timedelta(days=1)
    while d.strftime("%A") in service.settings()["closed_days"]:
        d += datetime.timedelta(days=1)
    return d.isoformat()


def test_slots_respect_bookings_break_and_closed_days():
    day = _next_open_day()
    free = service.free_slots(day)["free"]
    assert free and not any(s.startswith("13:30") or s.startswith("14:00") for s in free)   # lunch break
    sunday = datetime.date.today() + datetime.timedelta(days=(6 - datetime.date.today().weekday()) or 7)
    assert service.free_slots(sunday.isoformat())["free"] == []
    assert service.free_slots("2020-01-01")["free"] == []                                    # past


def test_booking_flow_and_double_booking():
    day = _next_open_day()
    slot = service.free_slots(day)["free"][0][:5]
    r = service.book_slot("Suresh", "Redmi Note 12", "screen", day, slot, "9000011111")
    assert r["booked"]
    again = service.book_slot("Other", "Phone", "x", day, slot, "9000022222")
    assert again["booked"] is False                                                           # no double booking
    assert service.my_bookings("9000011111")["bookings"]
    assert service.cancel_booking(r["booking_id"], "9000022222")["cancelled"] is False       # not their booking


def test_repair_status_only_own():
    assert service.repair_status("9876543210")["repairs"][0]["status"] == "Ready for pickup"
    assert service.repair_status("9000000001", "J1001")["found"] == 0


def test_agent_uses_tool_then_answers():
    llm = FakeLLM([{"tool_calls": [tool_call("repair_status")]}, {"content": "ನಿಮ್ಮ phone ready ಇದೆ."}])
    a = Agent(service.persona(), service.tools("9876543210"), "9876543210", llm)
    out = a.reply("ನನ್ನ phone ready ಆಯ್ತಾ?", "kn")
    assert detect_script_language(out) == "kn" and a.actions[0]["result"]["found"] == 1


def test_wrong_language_is_redone():
    llm = FakeLLM([{"content": "Your phone is ready."}, {"content": "ನಿಮ್ಮ phone ready ಇದೆ."}])
    a = Agent("x", [], "1", llm)
    assert detect_script_language(a.reply("ನನ್ನ phone?", "kn")) == "kn"


def test_connect_discovers_actions_with_safe_defaults(dashboard_url):
    r = connect.discover(dashboard_url, "demo-key-123")
    assert r["ok"] and r["actions"] == 6
    perms = {o["id"]: o["permission"] for o in connect.connection()["ops"]}
    assert perms["get_user"] == "allowed" and perms["recheck_kyc"] == "confirm" and perms["delete_user"] == "blocked"
    assert connect.discover(dashboard_url + "/nope", "x")["ok"] is False


def test_connect_privacy_and_actions(dashboard_url):
    connect.discover(dashboard_url, "demo-key-123")
    tools, guard = connect.tools("5550001111")              # a stranger
    t = {x.name: x for x in tools}
    assert "delete_user" not in t                               # blocked actions are never offered
    assert t["get_user"].fn(user_id="QK1003")["result"]["withheld"]
    assert "error" in t["recheck_kyc"].fn(user_id="QK1003")     # cannot change someone else's account
    assert t["verify_caller"].fn(record_id="QK1003", phone_last4="0000")["verified"] is False
    tools, guard = connect.tools("9988776655")               # the real owner
    t = {x.name: x for x in tools}
    assert t["find_user_by_phone"].fn(phone="9988776655")["result"]["user_id"] == "QK1003"
    assert t["recheck_kyc"].fn(user_id="QK1003")["result"]["kyc_status"] == "verified"


def test_verification_unlocks_record(dashboard_url):
    connect.discover(dashboard_url, "demo-key-123")
    tools, _ = connect.tools("5550001111")
    t = {x.name: x for x in tools}
    t["get_user"].fn(user_id="QK1002")
    assert t["verify_caller"].fn(record_id="QK1002", phone_last4="6780")["verified"]
    assert t["get_user"].fn(user_id="QK1002")["result"]["kyc_status"] == "pending"


def test_broken_dashboard_does_not_crash():
    conn = {"base_url": "http://127.0.0.1:1", "key_header": "X", "api_key": "k"}
    op = {"id": "x", "method": "GET", "path": "/u/{id}", "params": {"id": "string"}, "permission": "allowed"}
    assert "error" in connect.call_op(conn, op, {"id": "1"}, connect.Guard("1"))
