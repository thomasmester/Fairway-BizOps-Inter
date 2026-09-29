"""Classify one piece of customer form-review feedback with Claude.

The model reads the comment plus its context (form, field, customer, and the
other open tickets for the same customer + form) and returns a structured
triage decision: what the customer wants, what kind of error it is, how urgent
it is and who should fix it.
"""
import json
import os

import anthropic

MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5")
EFFORT = os.environ.get("CLAUDE_EFFORT", "medium")

CATEGORIES = [
    "mapping_error",         # field is filled from the wrong source data
    "condition_rule_error",  # a fill rule / condition is wrong or missing
    "customer_preference",   # a house practice, not a state rule
    "extraction_error",      # the document reading got the value wrong (OCR, parsing)
    "form_version",          # the form template itself is outdated or wrong
    "conflicting_feedback",  # contradicts another open comment
    "unclear",               # not enough information to act
    "not_an_error",          # the fill was correct
]
PRIORITIES = ["critical", "high", "medium", "low"]
ROUTES = ["form_editor", "extraction_team", "forms_team", "account_owner"]

SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "description": "What the customer is asking for, in one sentence."},
        "category": {"type": "string", "enum": CATEGORIES},
        "priority": {"type": "string", "enum": PRIORITIES},
        "priority_reason": {"type": "string"},
        "route_to": {"type": "string", "enum": ROUTES},
        "requires_mapping_change": {"type": "boolean"},
        "scope": {"type": "string", "enum": ["all_customers", "this_customer_only", "needs_verification"]},
        "affected_field": {"type": "string"},
        "error_summary": {"type": "string", "description": "What went wrong, written for the human form editor."},
        "suggested_fix": {"type": "string"},
        "verification_step": {"type": "string", "description": "What to check before changing anything."},
        "conflicts_with": {"type": "array", "items": {"type": "string"},
                           "description": "IDs of open tickets this comment contradicts. Empty if none."},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": ["intent", "category", "priority", "priority_reason", "route_to", "requires_mapping_change",
                 "scope", "affected_field", "error_summary", "suggested_fix", "verification_step",
                 "conflicts_with", "confidence"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """You triage customer feedback on DMV forms that Fairway Autofill filled in.

Context: Fairway's customers (fleets, dealers, auctions, tag agencies) upload vehicle and deal data, and Autofill fills out state DMV title and registration forms. Every form field has a mapping record: which piece of customer data fills it, plus rules such as "only fill if the vehicle is financed". During calibration, customer clerks review filled forms and leave comments. A human form editor acts on your triage, so be concrete and brief.

Decide what the comment means, then classify it:
- mapping_error: the field pulls the wrong data (for example lessee instead of lessor).
- condition_rule_error: a fill condition is wrong or missing (for example a lienholder filled on a cash sale).
- customer_preference: the customer wants something their house practice requires but the state may not. Treat it as a preference unless the comment makes clear it is a state rule; scope is then needs_verification.
- extraction_error: the value was misread from the customer's documents (for example a VIN with the letter O, which VINs never contain). This is not a mapping change; route it to extraction_team.
- form_version: the form template is outdated or the wrong form. Route to forms_team.
- conflicting_feedback: the comment contradicts an open ticket listed in the context. List those ticket IDs in conflicts_with, route to account_owner, and do not recommend a change until one answer is agreed.
- unclear or not_an_error when appropriate.

Priority:
- critical: every filing on this form is at risk of DMV rejection (outdated or wrong form), or the error affects all customers in a legally significant way.
- high: a legally significant field is wrong on filled forms (party names, VIN, lienholder, odometer, purchase price or tax), so filings may be rejected or titles issued incorrectly.
- medium: a decision or verification is needed before changing anything (preferences, conflicts, ambiguous rules).
- low: cosmetic, formatting or questions.

Never invent state rules. When the answer depends on a state rule you cannot confirm, say what to verify in verification_step and use scope needs_verification. Only list conflicts_with IDs that appear in the open tickets provided."""


class TriageError(Exception):
    """Raised when Claude cannot produce a usable triage decision."""


class ClaudeTriage:
    def __init__(self, client=None):
        self.client = client or anthropic.Anthropic(timeout=90.0, max_retries=2)

    def __call__(self, feedback: dict, open_tickets: list[dict]) -> dict:
        context = {
            "comment": feedback["comment"],
            "form": feedback.get("form") or "unknown",
            "field": feedback.get("field") or "unknown",
            "state": feedback.get("state") or "unknown",
            "customer": feedback.get("customer") or "unknown",
            "transaction_id": feedback.get("transaction_id") or "unknown",
            "open_tickets_same_customer_and_form": [
                {"id": t["id"], "field": t["affected_field"], "intent": t["intent"], "comment": t["comment"]}
                for t in open_tickets
            ],
        }
        try:
            response = self.client.beta.messages.create(
                model=MODEL,
                max_tokens=8000,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                system=SYSTEM_PROMPT,
                output_config={"effort": EFFORT, "format": {"type": "json_schema", "schema": SCHEMA}},
                messages=[{"role": "user", "content": "Triage this feedback:\n" + json.dumps(context, indent=2)}],
            )
        except anthropic.AuthenticationError as e:
            raise TriageError("Anthropic API key is missing or invalid.") from e
        except anthropic.RateLimitError as e:
            raise TriageError("Anthropic rate limit hit. Try again shortly.") from e
        except anthropic.APIStatusError as e:
            raise TriageError(f"Anthropic API error {e.status_code}: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise TriageError("Could not reach the Anthropic API.") from e

        if response.stop_reason == "refusal":
            raise TriageError("The model declined to triage this comment.")
        if response.stop_reason == "max_tokens":
            raise TriageError("The model ran out of tokens before finishing the triage.")
        texts = [b.text for b in response.content if b.type == "text"]
        if not texts:
            raise TriageError("The model returned no triage.")
        result = json.loads(texts[-1])
        known = {t["id"] for t in open_tickets}
        result["conflicts_with"] = [i for i in result["conflicts_with"] if i in known]
        result["model"] = response.model
        return result
