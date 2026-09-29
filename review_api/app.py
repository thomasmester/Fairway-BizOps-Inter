"""Form review triage API for Fairway Autofill.

Customers comment on filled forms during calibration. Each comment is sent to
Claude, which works out the intent and error type; the ticket is stored,
grouped by priority and the form editor is notified.

Run locally:  flask --app app run --debug
Production:   gunicorn app:app   (see render.yaml)
"""
import hmac
import logging
import os
import time
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from notify import notify
from store import PRIORITY_ORDER, Store
from triage import MODEL, ClaudeTriage, TriageError

HERE = Path(__file__).parent
FIELD_LIMITS = {"comment": 2000, "form": 120, "field": 120, "state": 60, "customer": 120,
                "transaction_id": 60, "submitted_by": 120}
STATUSES = {"open", "acknowledged", "resolved"}

logging.basicConfig(level=logging.INFO)


def create_app(classifier=None, db_path=None):
    app = Flask(__name__, static_folder=str(HERE / "static"), static_url_path="/static")
    db_path = db_path or os.environ.get("DATABASE_PATH", str(HERE / "data" / "reviews.db"))
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    store = Store(db_path)
    access_key = os.environ.get("APP_ACCESS_KEY", "")
    classify = classifier
    if classify is None and os.environ.get("ANTHROPIC_API_KEY"):
        classify = ClaudeTriage()

    def error(status, message):
        return jsonify({"error": message}), status

    @app.before_request
    def check_access():
        # Optional shared key so a public deployment can't be used to spend API credit.
        if access_key and request.path.startswith("/api/") and request.method != "GET":
            given = request.headers.get("X-Access-Key", "")
            if not hmac.compare_digest(given, access_key):
                return error(401, "Missing or wrong access key.")

    @app.get("/")
    def index():
        return send_from_directory(HERE / "static", "index.html")

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok", "model": MODEL, "classifier_ready": classify is not None,
                        "access_key_required": bool(access_key)})

    @app.post("/api/feedback")
    def create_feedback():
        body = request.get_json(silent=True) or {}
        feedback = {}
        for key, limit in FIELD_LIMITS.items():
            value = body.get(key)
            if value is None or value == "":
                continue
            if not isinstance(value, str):
                return error(400, f"'{key}' must be a string.")
            if len(value) > limit:
                return error(400, f"'{key}' is longer than {limit} characters.")
            feedback[key] = value.strip()
        if not feedback.get("comment"):
            return error(400, "'comment' is required.")
        if classify is None:
            return error(503, "No classifier configured. Set ANTHROPIC_API_KEY on the server.")

        open_tickets = store.open_tickets(feedback.get("customer"), feedback.get("form"))
        started = time.perf_counter()
        try:
            triage = classify(feedback, open_tickets)
        except TriageError as e:
            app.logger.warning("triage failed: %s", e)
            return error(502, str(e))
        triage_ms = round((time.perf_counter() - started) * 1000)
        ticket = store.create_ticket(feedback, triage)
        notify(store, ticket)
        return jsonify(ticket | {"triage_ms": triage_ms,
                                 "open_tickets_sent": [t["id"] for t in open_tickets]}), 201

    @app.get("/api/tickets")
    def list_tickets():
        return jsonify(store.list(request.args.get("status"), request.args.get("priority")))

    @app.get("/api/tickets/<tid>")
    def get_ticket(tid):
        ticket = store.get(tid)
        return jsonify(ticket) if ticket else error(404, "Ticket not found.")

    @app.patch("/api/tickets/<tid>")
    def update_ticket(tid):
        body = request.get_json(silent=True) or {}
        status = body.get("status")
        if status not in STATUSES:
            return error(400, f"'status' must be one of {sorted(STATUSES)}.")
        note = body.get("note")
        if note is not None and (not isinstance(note, str) or len(note) > 1000):
            return error(400, "'note' must be a string of at most 1000 characters.")
        ticket = store.update_status(tid, status, note)
        return jsonify(ticket) if ticket else error(404, "Ticket not found.")

    @app.get("/api/queue")
    def queue():
        """Open and acknowledged tickets, grouped by priority for the editor."""
        include_resolved = request.args.get("include_resolved") == "true"
        tickets = store.list()
        groups = {p: [] for p in PRIORITY_ORDER}
        for t in tickets:
            if include_resolved or t["status"] != "resolved":
                groups.setdefault(t["priority"], []).append(t)
        counts = {p: len(v) for p, v in groups.items()}
        return jsonify({"groups": groups, "counts": counts})

    @app.get("/api/notifications")
    def notifications():
        since = request.args.get("since", "0")
        return jsonify(store.notifications(int(since) if since.isdigit() else 0))

    @app.delete("/api/tickets")
    def clear_tickets():
        store.clear()
        return "", 204

    return app


app = create_app()
