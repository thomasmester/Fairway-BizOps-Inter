# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A Business Operations interview case study for Fairway Autofill. The case prompt is `bizops_analyst_prompt.pdf`, kept in the user's Downloads folder, not in the repo.
- **Part 1:** rank the top 10 states for form calibration (1 form per day).
- **Part 2:** design a customer-feedback → mapping-change process.

The approach is **traction-first**: prioritize states where existing customers already transact, especially the anchor customer 87, and treat pipeline $ and market size as tie-breakers. The reasoning is in `DECISIONS.md`. Keep that file in sync when weights or assumptions change.

## Commands

- `python analysis.py`: builds the scorecard, sensitivity check and calendar, and writes `output/*.csv`. It also prints the top 15 and the calendar.
- `python build_workbook.py`: writes `output/Fairway_State_Prioritization.xlsx`. It imports `analysis.py`, so both always use the same weights.
- Needs `pandas` and `openpyxl`. LibreOffice isn't installed, so the xlsx skill's `recalc.py` can't run here. Verify formulas with the `formulas` pip package instead (`formulas.ExcelModel().loads(path).finish().calculate()`), and compare to `output/state_scorecard.csv`.

## Structure

- `Data/`: inputs.
  - `transactions.csv`: 200 transactions, 5 days, 4 customers.
  - `sales_pipeline.csv`: 20 deals.
  - `market_data.csv`: FHWA MV-1 2023 registrations and 2025 new-vehicle sales. Sources are cited in `DECISIONS.md`.
- `analysis.py`: the single source of truth for the scoring settings.
  - `WEIGHTS`, `COMMITMENTS`, `HAIRCUTS`, `EXCLUDED` and `ANCHOR_CUSTOMER` sit at the top of the file.
  - Pipeline deals are split evenly across their states ("All 50" = 50 states).
  - Components are normalized to their max, then weighted.
- `build_workbook.py`: creates the Excel model.
  - Inputs are blue, judgment calls have yellow fill, and everything else is a live formula. Scorecard and Top 10 re-rank when the Weights tab changes.
  - The Calendar and Sensitivity tabs are snapshots from `analysis.py`.
- `.claude/skills/xlsx/`: a vendored copy of the xlsx skill (formatting conventions for the workbook).
- `artifacts/`: the source of every published artifact. Edit these files, then republish to the same URL; don't create new artifacts.
  - `artifacts/web/fairway_autofill_plan.html` is the HTML page (https://claude.ai/artifact/DX2JQAPb8PyTTuLrkUepMw). It embeds a JSON copy of the scorecard, so re-export the data if the weights or inputs change.
  - `artifacts/deck/project/` is the Slides deck (https://claude.ai/artifact/69DQS1MpGiqmrtiegpQDsG): `deck.json` plus one `slides/<id>.html` per slide.
  - To republish the deck, use the Artifact tool with `url` set to the deck, `root` set to `artifacts/deck`, and only the changed files.
  - Pie charts are inline SVG with paths computed in Python, and they use the dataviz skill's validated categorical palette in slot order.
- `review_api/`: the Part 2 Flask service, which triages form-review comments with Claude and queues them by priority.
  - `triage.py` holds the prompt and JSON schema.
  - `store.py` is SQLite storage.
  - `notify.py` sends the editor notifications (in-app, plus an optional webhook).
  - `static/index.html` is the demo page.
  - Tests: run `cd review_api && python -m unittest -v`. They use a stand-in classifier and a mocked SDK client, so they need no API key.
  - Run locally with `flask --app app run` and `ANTHROPIC_API_KEY` set.
  - Deploy with `render.yaml` at the repo root (a Render Blueprint). gunicorn doesn't run on Windows, so use Flask's dev server locally.
