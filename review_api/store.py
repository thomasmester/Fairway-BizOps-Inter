"""SQLite storage for triaged tickets and editor notifications."""
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    comment TEXT NOT NULL,
    form TEXT, field TEXT, state TEXT, customer TEXT, transaction_id TEXT, submitted_by TEXT,
    priority TEXT NOT NULL,
    category TEXT NOT NULL,
    route_to TEXT NOT NULL,
    affected_field TEXT,
    intent TEXT,
    triage TEXT NOT NULL,
    note TEXT
);
CREATE TABLE IF NOT EXISTS notifications (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    priority TEXT NOT NULL,
    route_to TEXT NOT NULL,
    message TEXT NOT NULL
);
"""


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path):
        self.path = path
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self):
        # sqlite3's own context manager commits but never closes; close explicitly.
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    @staticmethod
    def _ticket(row):
        t = dict(row)
        t["triage"] = json.loads(t["triage"])
        return t

    def open_tickets(self, customer, form):
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM tickets WHERE status != 'resolved' AND customer IS ? AND form IS ?",
                (customer, form)).fetchall()
        return [self._ticket(r) for r in rows]

    def create_ticket(self, feedback, triage):
        tid = "T-" + uuid.uuid4().hex[:6].upper()
        now = _now()
        with self._conn() as c:
            c.execute(
                """INSERT INTO tickets (id, created_at, updated_at, comment, form, field, state, customer,
                   transaction_id, submitted_by, priority, category, route_to, affected_field, intent, triage)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (tid, now, now, feedback["comment"], feedback.get("form"), feedback.get("field"),
                 feedback.get("state"), feedback.get("customer"), feedback.get("transaction_id"),
                 feedback.get("submitted_by"), triage["priority"], triage["category"], triage["route_to"],
                 triage["affected_field"], triage["intent"], json.dumps(triage)))
            # A conflict is symmetric: flag the earlier tickets too.
            for other in triage.get("conflicts_with", []):
                row = c.execute("SELECT triage FROM tickets WHERE id = ?", (other,)).fetchone()
                if row:
                    t = json.loads(row["triage"])
                    t["conflicts_with"] = sorted(set(t.get("conflicts_with", [])) | {tid})
                    c.execute("UPDATE tickets SET triage = ?, updated_at = ? WHERE id = ?",
                              (json.dumps(t), now, other))
        return self.get(tid)

    def get(self, tid):
        with self._conn() as c:
            row = c.execute("SELECT * FROM tickets WHERE id = ?", (tid,)).fetchone()
        return self._ticket(row) if row else None

    def list(self, status=None, priority=None):
        sql, args = "SELECT * FROM tickets WHERE 1=1", []
        if status:
            sql += " AND status = ?"
            args.append(status)
        if priority:
            sql += " AND priority = ?"
            args.append(priority)
        with self._conn() as c:
            rows = c.execute(sql + " ORDER BY created_at DESC", args).fetchall()
        tickets = [self._ticket(r) for r in rows]
        return sorted(tickets, key=lambda t: PRIORITY_ORDER.get(t["priority"], 9))

    def update_status(self, tid, status, note=None):
        with self._conn() as c:
            cur = c.execute("UPDATE tickets SET status = ?, note = COALESCE(?, note), updated_at = ? WHERE id = ?",
                            (status, note, _now(), tid))
        return self.get(tid) if cur.rowcount else None

    def add_notification(self, ticket, message):
        with self._conn() as c:
            c.execute("INSERT INTO notifications (ticket_id, created_at, priority, route_to, message) VALUES (?,?,?,?,?)",
                      (ticket["id"], _now(), ticket["priority"], ticket["route_to"], message))

    def notifications(self, since=0, limit=50):
        with self._conn() as c:
            rows = c.execute("SELECT * FROM notifications WHERE seq > ? ORDER BY seq DESC LIMIT ?",
                             (since, limit)).fetchall()
        return [dict(r) for r in rows]

    def clear(self):
        with self._conn() as c:
            c.execute("DELETE FROM tickets")
            c.execute("DELETE FROM notifications")
