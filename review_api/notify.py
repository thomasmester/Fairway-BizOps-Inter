"""Tell the human form editor about a new ticket.

Every ticket gets an in-app notification (shown on the demo page). Tickets at
or above NOTIFY_MIN_PRIORITY are also posted to NOTIFY_WEBHOOK_URL when it is
set; the payload's `text` field works with Slack and Teams incoming webhooks.
"""
import json
import logging
import os
import threading
import urllib.request

from store import PRIORITY_ORDER

log = logging.getLogger(__name__)

ROUTE_LABELS = {
    "form_editor": "Form editor",
    "extraction_team": "Extraction team",
    "forms_team": "Forms team",
    "account_owner": "Account owner",
}


def message_for(ticket):
    t = ticket["triage"]
    where = " · ".join(x for x in [ticket.get("state"), ticket.get("form"), t.get("affected_field")] if x)
    msg = f"[{ticket['priority'].upper()}] {where}: {t['error_summary']} Fix: {t['suggested_fix']}"
    if t.get("conflicts_with"):
        msg += f" Conflicts with {', '.join(t['conflicts_with'])}."
    return f"{msg} → {ROUTE_LABELS.get(ticket['route_to'], ticket['route_to'])} ({ticket['id']})"


def _post(url, text):
    try:
        req = urllib.request.Request(url, data=json.dumps({"text": text}).encode(),
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10).close()
    except Exception:  # a failed webhook must never fail the ticket
        log.exception("webhook notification failed")


def notify(store, ticket):
    text = message_for(ticket)
    store.add_notification(ticket, text)
    url = os.environ.get("NOTIFY_WEBHOOK_URL")
    threshold = PRIORITY_ORDER.get(os.environ.get("NOTIFY_MIN_PRIORITY", "high"), 1)
    if url and PRIORITY_ORDER.get(ticket["priority"], 9) <= threshold:
        threading.Thread(target=_post, args=(url, text), daemon=True).start()
