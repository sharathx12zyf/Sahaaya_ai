"""QuickKart Admin: a SAMPLE company dashboard (users, KYC, orders) with its own API.
It stands in for any real company's dashboard that Sahaaya connects to.
API docs (auto): http://localhost:9000/openapi.json   Key: header X-API-Key (default demo-key-123)."""
import datetime
import os
import random

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse

API_KEY = os.environ.get("DASHBOARD_API_KEY", "demo-key-123")
app = FastAPI(title="QuickKart Admin API", version="1.0",
              description="Customer accounts, KYC verification and orders of QuickKart.")
today = datetime.date.today()
D = lambda n: (today + datetime.timedelta(days=n)).isoformat()

USERS = {
    "QK1001": {"user_id": "QK1001", "name": "Ravi Kumar", "phone": "9876543210", "kyc_status": "verified",
               "kyc_issue": "", "kyc_submitted": D(-20)},
    "QK1002": {"user_id": "QK1002", "name": "Lakshmi N", "phone": "9123456780", "kyc_status": "pending",
               "kyc_issue": "PAN card photo is blurry", "kyc_submitted": D(-4), "docs_ok_on_recheck": False},
    "QK1003": {"user_id": "QK1003", "name": "Arun S", "phone": "9988776655", "kyc_status": "pending",
               "kyc_issue": "Verification stuck in queue (documents are fine)", "kyc_submitted": D(-6),
               "docs_ok_on_recheck": True},
    "QK1004": {"user_id": "QK1004", "name": "Fatima Begum", "phone": "9845012345", "kyc_status": "not_started",
               "kyc_issue": "No documents uploaded", "kyc_submitted": None},
}
ORDERS = {
    "ORD501": {"order_id": "ORD501", "user_id": "QK1001", "item": "Wireless earbuds", "status": "out_for_delivery",
               "expected": D(0), "hold_reason": ""},
    "ORD502": {"order_id": "ORD502", "user_id": "QK1002", "item": "Smart watch", "status": "on_hold",
               "expected": D(-2), "hold_reason": "KYC pending: orders above 5,000 rupees need verified KYC"},
    "ORD503": {"order_id": "ORD503", "user_id": "QK1003", "item": "Laptop bag", "status": "on_hold",
               "expected": D(-1), "hold_reason": "KYC pending"},
    "ORD504": {"order_id": "ORD504", "user_id": "QK1004", "item": "Mixer grinder", "status": "on_hold",
               "expected": D(1), "hold_reason": "KYC not started"},
}
LOG = []


def auth(x_api_key: str = Header("")):
    if x_api_key != API_KEY:
        raise HTTPException(401, "invalid API key")


def _user(user_id):
    u = USERS.get(user_id.upper())
    if not u:
        raise HTTPException(404, "user not found")
    return u


@app.get("/api/users/by-phone/{phone}", dependencies=[Depends(auth)], operation_id="find_user_by_phone",
         summary="Find a customer account by registered phone number")
def by_phone(phone: str):
    p = "".join(c for c in phone if c.isdigit())[-10:]
    for u in USERS.values():
        if u["phone"] == p:
            return {k: v for k, v in u.items() if k != "docs_ok_on_recheck"}
    raise HTTPException(404, "no account with this phone")


@app.get("/api/users/{user_id}", dependencies=[Depends(auth)], operation_id="get_user",
         summary="Get a customer account and KYC status by user ID")
def get_user(user_id: str):
    return {k: v for k, v in _user(user_id).items() if k != "docs_ok_on_recheck"}


@app.get("/api/users/{user_id}/orders", dependencies=[Depends(auth)], operation_id="list_user_orders",
         summary="List a customer's orders with status, expected date and hold reason")
def orders(user_id: str):
    _user(user_id)
    return [o for o in ORDERS.values() if o["user_id"] == user_id.upper()]


@app.post("/api/users/{user_id}/kyc/recheck", dependencies=[Depends(auth)], operation_id="recheck_kyc",
          summary="Re-run KYC verification for a customer (approves if documents are fine) and release held orders")
def recheck(user_id: str):
    u = _user(user_id)
    if u["kyc_status"] == "verified":
        return {"kyc_status": "verified", "message": "Already verified"}
    if u.get("docs_ok_on_recheck"):
        u.update(kyc_status="verified", kyc_issue="")
        released = []
        for o in ORDERS.values():
            if o["user_id"] == u["user_id"] and o["status"] == "on_hold":
                o.update(status="processing", hold_reason="", expected=D(2))
                released.append(o["order_id"])
        LOG.append(f"KYC re-check approved for {u['user_id']}")
        return {"kyc_status": "verified", "orders_released": released, "new_expected_delivery": D(2)}
    LOG.append(f"KYC re-check failed for {u['user_id']}")
    return {"kyc_status": u["kyc_status"], "message": f"Still not verified: {u['kyc_issue']}. Customer must re-upload."}


@app.post("/api/users/{user_id}/kyc/send-upload-link", dependencies=[Depends(auth)], operation_id="send_kyc_upload_link",
          summary="Send the customer an SMS link to upload or re-upload KYC documents")
def send_link(user_id: str):
    u = _user(user_id)
    LOG.append(f"KYC upload link sent to {u['user_id']}")
    return {"sent": True, "channel": "SMS", "link_valid_hours": 24,
            "steps": ["Open the SMS link", "Upload a clear photo of PAN card and Aadhaar",
                      "Take a selfie", "Verification usually completes within 2 hours"]}


@app.delete("/api/users/{user_id}", dependencies=[Depends(auth)], operation_id="delete_user",
            summary="Permanently delete a customer account")
def delete_user(user_id: str):
    USERS.pop(user_id.upper(), None)
    return {"deleted": True}


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def page():
    rows = "".join(f"<tr><td>{u['user_id']}</td><td>{u['name']}</td><td>{u['phone'][:2]}******{u['phone'][-2:]}</td>"
                   f"<td class='{u['kyc_status']}'>{u['kyc_status']}</td><td>{u['kyc_issue']}</td></tr>" for u in USERS.values())
    orows = "".join(f"<tr><td>{o['order_id']}</td><td>{o['user_id']}</td><td>{o['item']}</td>"
                    f"<td class='{o['status']}'>{o['status']}</td><td>{o['expected']}</td><td>{o['hold_reason']}</td></tr>"
                    for o in ORDERS.values())
    log = "".join(f"<li>{x}</li>" for x in LOG[-8:]) or "<li>No actions yet</li>"
    return f"""<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<meta http-equiv=refresh content=4><title>QuickKart Admin</title>
<style>body{{font-family:system-ui;margin:24px;background:#f6f7fb;color:#1d2230}}table{{border-collapse:collapse;width:100%;background:#fff;margin-bottom:24px}}
td,th{{padding:8px 10px;border-bottom:1px solid #e5e7ef;text-align:left;font-size:14px}}th{{background:#eef0f7}}
.verified,.processing,.out_for_delivery{{color:#0a7d32;font-weight:600}}.pending,.on_hold,.not_started{{color:#b45309;font-weight:600}}</style>
<h1>QuickKart Admin <small style="font-size:14px;color:#667">sample company dashboard &middot; auto-refreshes</small></h1>
<h3>Customers &amp; KYC</h3><table><tr><th>User ID</th><th>Name</th><th>Phone</th><th>KYC</th><th>Issue</th></tr>{rows}</table>
<h3>Orders</h3><table><tr><th>Order</th><th>User</th><th>Item</th><th>Status</th><th>Expected</th><th>Hold reason</th></tr>{orows}</table>
<h3>Recent actions by API (e.g. Sahaaya agent)</h3><ul>{log}</ul>"""
