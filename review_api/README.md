# Autofill Review Desk (API + demo)

A Flask API that turns customer comments on filled DMV forms into prioritized tickets for the human form editor. This implements the Part 2 process from the case: Capture → Classify → Verify → Scope → Change → Test → Close the loop.

1. **Capture:** `POST /api/feedback` takes the comment plus its context (customer, state, form, field, transaction).
2. **Classify:** Claude (`claude-opus-5`, structured JSON output) works out:
   - the customer's intent;
   - the error category: mapping, fill rule, customer preference, extraction, form version or conflicting;
   - the priority (critical / high / medium / low);
   - who should act, whether a mapping change is needed and what to verify first.
3. **Conflicts:** the other open tickets for the same customer and form are sent along. A contradicting comment, like the two clerks disagreeing about dealer fees, is linked to the earlier ticket in both directions and routed to the account owner.
4. **Notify:** every ticket posts an editor notification. Tickets at or above `NOTIFY_MIN_PRIORITY` also go to `NOTIFY_WEBHOOK_URL` (a Slack or Teams incoming webhook) when it's set.
5. **Queue:** `GET /api/queue` returns open tickets grouped by priority. The demo page at `/` shows them as a four-column board with Acknowledge / Resolve buttons.

## Run locally

```bash
cd review_api
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...        # PowerShell: $env:ANTHROPIC_API_KEY="sk-ant-..."
flask --app app run --debug               # open http://127.0.0.1:5000
python -m unittest -v                     # tests use a stand-in classifier, no API calls
```

On the demo page, "Run all 7 examples" sends the six comments from the case, plus the second clerk's opposite comment on dealer fees. That's 7 Claude calls.

## Deploy on Render

1. Push the repo to GitHub.
2. In Render, choose **New → Blueprint** and pick the repo. `render.yaml` at the repo root defines the service (root dir `review_api`, gunicorn start command, health check `/api/health`).
3. Set the secret environment variables when prompted:
   - `ANTHROPIC_API_KEY` (required)
   - `APP_ACCESS_KEY` (recommended). When it's set, every write request needs the header `X-Access-Key`, so strangers can't spend your API credit. The demo page shows a field for it.
   - `NOTIFY_WEBHOOK_URL` (optional)

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Demo page |
| GET | `/api/health` | Status, model, whether a key is configured |
| POST | `/api/feedback` | Triage a comment → `201` with the ticket |
| GET | `/api/queue` | Open tickets grouped by priority (`?include_resolved=true` to include resolved ones) |
| GET | `/api/tickets` | List tickets (`?status=`, `?priority=`) |
| GET / PATCH | `/api/tickets/<id>` | Read a ticket, or set `{"status": "open" \| "acknowledged" \| "resolved", "note": "..."}` |
| GET | `/api/notifications` | Editor notifications (`?since=<seq>` for new ones only) |
| DELETE | `/api/tickets` | Clear all demo data |

Example:

```bash
curl -X POST https://<your-app>.onrender.com/api/feedback \
  -H "Content-Type: application/json" -H "X-Access-Key: $APP_ACCESS_KEY" \
  -d '{"customer":"Customer 87","state":"Arizona","form":"AZ title application",
       "field":"Lienholder section","comment":"Why is the lienholder section filled in? This vehicle was paid in cash."}'
```

## Configuration

| Variable | Default | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | none | Required for triage. Without it, `POST /api/feedback` returns 503. |
| `CLAUDE_MODEL` | `claude-opus-5` | |
| `CLAUDE_EFFORT` | `medium` | `low` is cheaper and faster; `high` is more careful. |
| `APP_ACCESS_KEY` | none | Guards every write request when set. |
| `NOTIFY_WEBHOOK_URL` | none | Receives `{"text": "..."}` for tickets at or above the threshold. |
| `NOTIFY_MIN_PRIORITY` | `high` | `critical`, `high`, `medium` or `low` |
| `DATABASE_PATH` | `data/reviews.db` | SQLite file |

## Limits

- **Storage:** on Render's free plan the filesystem is wiped on every deploy or restart, so tickets don't persist. For real use, point the store at Postgres or attach a Render disk.
- **Single worker:** the service runs one gunicorn worker (with threads) so everything shares one SQLite file.
- **Fallbacks:** requests opt into Anthropic's server-side fallbacks (`fallbacks: "default"`). If Claude Opus 5 declines a comment, the API retries it on a fallback model instead of failing.
