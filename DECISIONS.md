# Design decisions: Fairway Autofill state prioritization

This file records every judgment call behind the ranking, so each can be defended or changed in the debrief. The numbers come from `analysis.py`. The live, editable version is `output/Fairway_State_Prioritization.xlsx`.

## Result

| # | State | Why |
|---|---|---|
| 1 | Texas | 64 of the 200 transactions (32%), from 3 existing customers. D02 explicitly wants Texas live first. D03's POC ($420k) is scored on Autofill accuracy. |
| 2 | Alabama | Customer 87's #2 state (13 transactions). D09 is signed, with Autofill promised for Q4. |
| 3 | Arizona | 14 transactions (customers 87 and 90). Part of D02 (80%). |
| 4 | Georgia | 9 transactions from customer 87. D09 signed, Q4 promise. |
| 5 | Florida | 19 transactions (customer 121 + 87). Part of D02 (80%). |
| 6 | Tennessee | Only 3 transactions, but a contractual Q4 promise to D09, a signed customer. |
| 7 | Colorado | 13 transactions from customer 87, and no commitment. A pure usage pick. |
| 8 | Virginia | The one pipeline-driven pick: D07 ($1.5M, 75%), where Autofill is a must-have to sign. 1 transaction today. |
| 9 | California | 4 transactions from customer 87. The largest US market breaks the tie with PA, IL and AR. |
| 10 | Pennsylvania | 5 transactions from customer 87. Also D20 (60%) and D14, and D19 was lost for lacking Autofill. |

- **Bubble:** Arkansas (#11, 6 transactions from customer 87) is the first swap-in. It's in the top 10 in 3 of 11 sensitivity scenarios.
- **Coverage:** the top 10 cover **72.5%** of recent transactions, and **60%** of the anchor customer's.
- **Calendar:** at 1 form per day this is **20 working days** (2 forms per state).
  - After day 6 (TX New + Used, then the main form in AL, AZ, GA and FL), **55%** of recent volume is calibrated.

## Decision 1: Optimize for traction, not pipeline dollars
**Decision:** Existing-customer usage and existing-customer commitments carry 85% of the score. Pipeline is 10%, market size 5%.

**Why:** Autofill is a new product with zero mapped forms. What de-risks it is live customers submitting real transactions through it. They generate the calibration feedback (Part 2), prove accuracy and become references for new logos. A new-logo deal with a large headline number (D10 $2.5M, D08 $2M) doesn't generate usage until it closes, and most of those deals are early-stage or conditional. Existing customers already trust us through Audit, so they're the fastest path to adoption.

**What would change it:** leadership might decide the priority is closing a specific large deal this quarter (for example D07 Virginia). Then raise the pipeline weight on the Weights tab. Virginia is already #8.

## Decision 2: Anchor on customer 87 (our biggest account)
**Decision:** A separate 20% component for customer 87's transactions, on top of the general volume component (45%).

**Why:** Customer 87:
- is 68% of the sample (136 of 200 transactions, across 36 states);
- already uses Audit in 30+ states;
- has an open Autofill expansion (D01, $180k, 60%).

They bring us the most business elsewhere, so their states are where Autofill adoption would move the most volume, and the account most worth protecting. The general volume component alone would over-index on Texas and Florida, where customers 110 and 121 operate. The anchor component lifts states like Alabama, Colorado and Georgia, where 87 is concentrated.

## Decision 3: Commitments to existing customers are an explicit input
| State | Score | Basis |
|---|---|---|
| TX | 1.0 | D02 (existing customers 110 / 121): pricing agreed, "wants Texas live first" |
| GA, AL, TN | 1.0 | D09 (Peach State Motors): Closed Won, "Autofill promised for Q4" |
| FL, AZ | 0.8 | D02 at 80%, pricing agreed |

**Why:** a promise to a signed customer is a delivery obligation, not a sales opportunity. Missing it damages trust in the product at launch. New-logo deals (D07, D17, D20…) are deliberately not treated as commitments. They enter through the pipeline component.

## Decision 4: Pipeline value is probability-weighted, haircut, and Autofill-only
- **Adjusted value** = annual value × rep probability × haircut, then split evenly across the deal's states. "All 50" = 50 states.
- **Excluded:**
  - D10 ($2.5M): the products are Audit only, so it creates no Autofill calibration need.
  - D13 and D19: Closed Lost.
- **Haircuts:**

  | Deal | Haircut | Reason |
  |---|---|---|
  | D06 ($1.2M, all 50) | 25% | Expected close 2026-06-30 is already past, and it's been stuck in legal since May. |
  | D05 ($900k) | 50% | Discovery stage; the amount is the rep's estimate after one call. |
  | D08 ($2M, MD) | 50% | Depends on a state fee bill passing. |

- **Signal, not score:** D19 (NY / NJ / PA) was lost *because we had no Autofill*. That's demand evidence for PA / NJ / NY, and it's noted in PA's rationale.
- **Why:** rep probabilities are unaudited, and several deals carry red flags in the notes. Without these adjustments, D06, D10 and D08 would dominate the pipeline component on paper value alone.

## Decision 5: Market size is a tie-breaker only (5%)
**Sources:**
- FHWA Highway Statistics 2023, Table MV-1, total motor vehicles: https://www.fhwa.dot.gov/policyinformation/statistics/2023/pdf/mv1.pdf
- 2025 new-vehicle sales by state (F&I Tools report): https://www.factorywarrantylist.com/car-sales-by-state.html

The market component is the average of the two, each normalized to its maximum.

**Why only 5%:** market size tells us about long-run TAM, not about which form to calibrate this week. At 5% it only separates states with similar usage. For example, California (4 transactions) edges out Pennsylvania, Illinois and Arkansas (5–6 transactions).

**Known issue:** Oklahoma's 2025 sales figure looks inflated relative to its registrations. It doesn't affect the top 10.

## Decision 6: The unit of work is a form, not a state
**Decision:** calibration capacity is 1 form per day, so the plan is sequenced by form (state × transaction type).
- **Assumption:** each state needs 2 forms, new-vehicle title and used / transfer title. This needs to be confirmed per state.
- **Wave 1:** the highest-volume form in each top-10 state, in rank order. Texas gets both forms up front because D02 asked for Texas "live first".
- **Wave 2:** the remaining forms, by volume.

**Why:** the new / used mix differs sharply by state. TX is 53 new vs 11 used, while AZ and AL are mostly used. Calibrating the main form first gets the most transactions onto Autofill soonest.

## Decision 7: Normalize each component to its max, then take a weighted sum
**Decision:** each component is divided by its maximum across states (0–1), then weighted.
- Commitment is already on a 0–1 scale.
- Ties break on raw transaction count.

**Why:** it's simple, transparent and easy to reproduce in Excel. The debrief audience can change a weight and immediately see the re-rank.

**Robustness:** shifting each weight ±10pp (11 scenarios) keeps 8 states in the top 10 in every scenario. California and Virginia are in 10 and 9 scenarios, and Arkansas replaces one of them in 3.

## Data limitations
- **Only 5 days of transactions** (Sep 24–28), including a weekend. That's too short to capture seasonality or monthly volume.
- **Concentration:** one customer is 68% of the sample. The ranking reflects that on purpose (Decision 2), but it's also a risk if 87 churns or its mix shifts.
- **All four customers in the sample are existing customers** "interested in Autofill". There are no transactions from pipeline prospects.
- **Rep probabilities are self-reported** and uncalibrated.

## What I'd want to know before committing
1. **How many forms does each state actually need?** And can mappings be reused across states with similar forms? This changes the number of days per state.
2. **Is the 5-day sample representative?** I'd want 3–6 months of transaction history per customer and state.
3. **Customer 87's intent:** does D01 cover all 36 states they file in, and which states would they switch to Autofill first?
4. **Hard dates:** the D09 Q4 deadline, D03's POC scoring date, and when D07 needs Autofill live to sign.
5. **Can Audit's existing state rule sets speed up calibration** in states where Audit is already live?
6. **Are form changes pending** at the DMVs? A form about to change is a poor first calibration target.
7. **How accurate are the reps' historical close probabilities?**

## Part 2: feedback process (summary)
The steps are Capture → Classify → Verify → Scope → Change → Test → Close the loop. The workbook's Feedback Process tab has the full triage of the six examples. The key principles:
- **Not all feedback is a mapping change.**
  - The VIN O / 0 error (example 3) is an extraction bug. It needs a VIN validation check, not a mapping edit.
  - The stale form (example 4) needs form versioning and monitoring of DMV form changes.
- **State rule vs customer preference.** The odometer comment (example 2) may be a state exemption, which would be a global conditional rule. Or it may be a house habit, which would be a per-customer override. Verify against the DMV rule before choosing.
- **Conflicting feedback (example 5) never goes straight into a mapping.** Resolve it against the state's definition of the purchase price and get one answer from the customer's admin.
- **Every change is regression-tested** on past transactions before it's published. The repeat-error rate per form is the calibration quality KPI.

## Part 2 prototype: the Review Desk API (`review_api/`)
The Capture and Classify steps are automated. A human still owns Verify, Scope and Change.

| Decision | Why |
|---|---|
| Claude classifies intent, category, priority and route, into a fixed JSON schema | Comments are free text; the editor needs structured, sortable tickets. A fixed schema (structured outputs) means the queue never gets a malformed ticket. |
| The model says what to verify, but never decides a state rule | "Leave the odometer blank" could be a state exemption or a house habit. The model flags that it needs checking (scope `needs_verification`) rather than guessing. |
| Open tickets for the same customer and form go into the prompt | Lets the model catch conflicting feedback (example 5) and link both tickets, instead of letting the second clerk silently overwrite the first. Invented ticket IDs are filtered out. |
| Four priorities: critical (every filing at risk, e.g. an old form version), high (a legally significant field is wrong), medium (needs a decision), low (cosmetic) | Mirrors the cost of the error: DMV rejections and wrong titles first, preferences and debates after. |
| Extraction errors route to the extraction team, form versions to the forms team, conflicts to the account owner | Not every comment is a mapping edit. The form editor's queue stays focused on real mapping work. |
| Notifications go in-app for every ticket, and to a webhook only for high and above | Editors see everything on the board, but only urgent items interrupt them. |
| `claude-opus-5` at medium effort, with server-side fallbacks | A strong model for nuanced intent. Fallbacks keep the queue flowing if a request is declined. Effort is configurable to trade cost against care. |
| An optional shared access key on write requests | The Render URL is public, and each triage costs API credit. |
