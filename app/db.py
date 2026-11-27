"""SQLite storage shared by both sections."""
import json
import os
import sqlite3
import threading

from .config import DATA_DIR

_LOCK = threading.Lock()
PATH = os.path.join(DATA_DIR, "vaani.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS appointments (
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, phone TEXT, device TEXT, issue TEXT,
  start TEXT, status TEXT DEFAULT 'booked', created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY, phone TEXT, name TEXT, device TEXT, issue TEXT, status TEXT,
  amount INTEGER, ready_by TEXT);
CREATE TABLE IF NOT EXISTS tickets (
  id TEXT PRIMARY KEY, section TEXT, phone TEXT, issue TEXT, details TEXT,
  urgent INTEGER DEFAULT 0, status TEXT DEFAULT 'open', created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS calls (
  id TEXT PRIMARY KEY, section TEXT, caller TEXT, lang TEXT, transcript TEXT, actions TEXT,
  created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS notifications (
  id INTEGER PRIMARY KEY AUTOINCREMENT, section TEXT, text TEXT, seen INTEGER DEFAULT 0,
  created TEXT DEFAULT CURRENT_TIMESTAMP);
"""


def conn():
    c = sqlite3.connect(PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init():
    with _LOCK, conn() as c:
        c.executescript(SCHEMA)


def q(sql, args=(), one=False):
    with _LOCK, conn() as c:
        cur = c.execute(sql, args)
        rows = [dict(r) for r in cur.fetchall()]
        c.commit()
    return (rows[0] if rows else None) if one else rows


def run(sql, args=()):
    with _LOCK, conn() as c:
        cur = c.execute(sql, args)
        c.commit()
        return cur.lastrowid


def get(key, default=None):
    r = q("SELECT v FROM kv WHERE k=?", (key,), one=True)
    return json.loads(r["v"]) if r else default


def put(key, value):
    run("INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
        (key, json.dumps(value, ensure_ascii=False)))


def notify(section, text):
    run("INSERT INTO notifications(section,text) VALUES(?,?)", (section, text))
