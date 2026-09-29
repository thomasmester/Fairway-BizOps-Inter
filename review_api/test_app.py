"""API tests with a stand-in classifier (no Anthropic calls). Run: python -m unittest -v"""
import os
import tempfile
import unittest
from unittest import mock

from app import create_app
from notify import message_for


def fake_classifier(feedback, open_tickets):
    """Deterministic stand-in for Claude, keyed on words in the comment."""
    text = feedback["comment"].lower()
    base = {"intent": "x", "priority_reason": "x", "requires_mapping_change": True, "scope": "all_customers",
            "affected_field": feedback.get("field", ""), "error_summary": "Something is wrong.",
            "suggested_fix": "Fix it.", "verification_step": "Check it.", "conflicts_with": [],
            "confidence": "high", "route_to": "form_editor"}
    if "old version" in text:
        return base | {"category": "form_version", "priority": "critical", "route_to": "forms_team"}
    if "dealer fees" in text:
        conflicts = [t["id"] for t in open_tickets if t["affected_field"] == feedback.get("field")]
        cat = "conflicting_feedback" if conflicts else "customer_preference"
        return base | {"category": cat, "priority": "medium", "conflicts_with": conflicts,
                       "route_to": "account_owner" if conflicts else "form_editor"}
    return base | {"category": "mapping_error", "priority": "high"}


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app(classifier=fake_classifier, db_path=os.path.join(self.tmp.name, "t.db"))
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def post(self, **body):
        return self.client.post("/api/feedback", json=body)

    def test_comment_is_required(self):
        self.assertEqual(self.post(form="GA").status_code, 400)

    def test_overlong_comment_rejected(self):
        self.assertEqual(self.post(comment="x" * 2001).status_code, 400)

    def test_ticket_is_created_notified_and_grouped(self):
        r = self.post(comment="This is the old version of the form.", form="FL title", state="Florida")
        self.assertEqual(r.status_code, 201)
        ticket = r.get_json()
        self.assertEqual(ticket["priority"], "critical")
        queue = self.client.get("/api/queue").get_json()
        self.assertEqual(queue["counts"], {"critical": 1, "high": 0, "medium": 0, "low": 0})
        notes = self.client.get("/api/notifications").get_json()
        self.assertEqual(len(notes), 1)
        self.assertIn("[CRITICAL]", notes[0]["message"])
        self.assertIn(ticket["id"], notes[0]["message"])

    def test_conflicting_feedback_links_both_tickets(self):
        common = {"customer": "Customer 87", "form": "GA title", "field": "Purchase price"}
        first = self.post(comment="Price should include the dealer fees.", **common).get_json()
        second = self.post(comment="Price should not include the dealer fees.", **common).get_json()
        self.assertEqual(second["triage"]["conflicts_with"], [first["id"]])
        first_again = self.client.get(f"/api/tickets/{first['id']}").get_json()
        self.assertEqual(first_again["triage"]["conflicts_with"], [second["id"]])

    def test_resolved_tickets_leave_the_queue(self):
        tid = self.post(comment="Box 12 should be the lessor.").get_json()["id"]
        r = self.client.patch(f"/api/tickets/{tid}", json={"status": "resolved", "note": "Remapped"})
        self.assertEqual(r.get_json()["status"], "resolved")
        self.assertEqual(self.client.get("/api/queue").get_json()["counts"]["high"], 0)
        self.assertEqual(self.client.get("/api/queue?include_resolved=true").get_json()["counts"]["high"], 1)

    def test_bad_status_rejected(self):
        tid = self.post(comment="Box 12 should be the lessor.").get_json()["id"]
        self.assertEqual(self.client.patch(f"/api/tickets/{tid}", json={"status": "done"}).status_code, 400)

    def test_no_classifier_returns_503(self):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}):
            app = create_app(db_path=os.path.join(self.tmp.name, "n.db"))
        r = app.test_client().post("/api/feedback", json={"comment": "hello"})
        self.assertEqual(r.status_code, 503)

    def test_access_key_guards_writes_only(self):
        with mock.patch.dict(os.environ, {"APP_ACCESS_KEY": "s3cret"}):
            app = create_app(classifier=fake_classifier, db_path=os.path.join(self.tmp.name, "k.db"))
        c = app.test_client()
        self.assertEqual(c.post("/api/feedback", json={"comment": "Box 12"}).status_code, 401)
        self.assertEqual(c.post("/api/feedback", json={"comment": "Box 12"},
                                headers={"X-Access-Key": "s3cret"}).status_code, 201)
        self.assertEqual(c.get("/api/queue").status_code, 200)

    def test_demo_page_served(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Autofill Review Desk", r.data)
        r.close()

    def test_message_format(self):
        ticket = {"id": "T-1", "priority": "high", "route_to": "form_editor", "state": "Texas", "form": "TX title",
                  "triage": {"affected_field": "Box 12", "error_summary": "Lessee in lessor box.",
                             "suggested_fix": "Map lessor name.", "conflicts_with": []}}
        self.assertEqual(message_for(ticket),
                         "[HIGH] Texas · TX title · Box 12: Lessee in lessor box. Fix: Map lessor name. → Form editor (T-1)")


class ClaudeTriageTest(unittest.TestCase):
    """Checks the request we send and how the response is parsed, using a mocked SDK client."""

    def make(self, stop_reason="end_turn", text=None):
        import json
        from types import SimpleNamespace
        from triage import ClaudeTriage
        payload = text if text is not None else json.dumps(
            fake_classifier({"comment": "old version", "field": "Whole form"}, []) | {"conflicts_with": ["T-KEEP", "T-MADEUP"]})
        response = SimpleNamespace(stop_reason=stop_reason, model="claude-opus-5",
                                   content=[SimpleNamespace(type="thinking", thinking=""),
                                            SimpleNamespace(type="text", text=payload)])
        client = mock.MagicMock()
        client.beta.messages.create.return_value = response
        return ClaudeTriage(client=client), client

    def test_request_shape_and_parsing(self):
        triage, client = self.make()
        result = triage({"comment": "This is the old version of the form.", "form": "FL"},
                        [{"id": "T-KEEP", "affected_field": "Whole form", "intent": "x", "comment": "y"}])
        kwargs = client.beta.messages.create.call_args.kwargs
        self.assertEqual(kwargs["model"], "claude-opus-5")
        self.assertEqual(kwargs["fallbacks"], "default")
        self.assertIn("server-side-fallback-2026-07-01", kwargs["betas"])
        self.assertEqual(kwargs["output_config"]["format"]["type"], "json_schema")
        self.assertIn("T-KEEP", kwargs["messages"][0]["content"])
        self.assertEqual(result["category"], "form_version")
        self.assertEqual(result["conflicts_with"], ["T-KEEP"])  # invented IDs are dropped

    def test_refusal_raises(self):
        from triage import TriageError
        triage, _ = self.make(stop_reason="refusal")
        with self.assertRaises(TriageError):
            triage({"comment": "x"}, [])


if __name__ == "__main__":
    unittest.main()
