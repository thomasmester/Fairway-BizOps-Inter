"""Build output/Fairway_State_Prioritization.xlsx from Data/ and analysis.py.

The Scorecard is live: weights, commitments, haircuts and raw data are inputs
(blue text), everything else is an Excel formula. Run analysis.py's logic first
so the calendar and sensitivity snapshots match the base weights.
"""
from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

import analysis as A

FONT = "Arial"
BLUE = Font(name=FONT, color="0000FF")
BLACK = Font(name=FONT)
BOLD = Font(name=FONT, bold=True)
TITLE = Font(name=FONT, bold=True, size=14)
SUB = Font(name=FONT, italic=True, color="555555")
HEAD = Font(name=FONT, bold=True, color="FFFFFF")
HEAD_FILL = PatternFill("solid", fgColor="1F3864")
YELLOW = PatternFill("solid", fgColor="FFFF00")
TOP_FILL = PatternFill("solid", fgColor="E2EFDA")
WRAP = Alignment(wrap_text=True, vertical="top")
THIN = Border(bottom=Side(style="thin", color="BFBFBF"))

USD = '$#,##0;($#,##0);"-"'
PCT = '0.0%;(0.0%);"-"'
NUM = '#,##0;(#,##0);"-"'
SCORE = '0.000;(0.000);"-"'

RATIONALE = {
    "Texas": "Largest usage (32% of transactions) from 3 existing customers; D02 explicitly wants Texas live first; D03 POC ($420k) is scored on Autofill accuracy.",
    "Alabama": "Anchor customer 87's #2 state (13 txns, mostly used); D09 is signed with Autofill promised for Q4.",
    "Arizona": "14 txns from customers 87 and 90; part of D02 (80%) and D17 (70%, new logo).",
    "Georgia": "9 txns from customer 87; D09 signed deal (Peach State) with Autofill promised for Q4.",
    "Florida": "2nd-highest usage (19 txns, customer 121 + 87); part of D02 at 80%.",
    "Tennessee": "Low current usage (3) but a contractual Q4 promise to D09, a signed customer.",
    "Colorado": "Customer 87's joint #2 state (13 txns) with no commitment; pure usage pick.",
    "Virginia": "The one pipeline-driven pick: D07 ($1.5M, 75%) says Autofill is a must-have to sign. Only 1 txn today. Debate item.",
    "California": "4 txns from customer 87; largest US market breaks the tie with PA/IL/AR.",
    "Pennsylvania": "5 txns from customer 87; D20 (Legal Review, 60%) and D14; D19 was lost for lacking Autofill.",
    "Arkansas": "Bubble: 6 txns from customer 87 but a small market and no pipeline. First swap-in.",
    "Illinois": "Bubble: 5 txns from customer 87; only pipeline is D10, which is Audit only.",
}

FEEDBACK = [
    (1, "Box 12 should have the lessor's name, not the lessee's.", "Mapping error (wrong source field)",
     "Mapping points at lessee instead of lessor.", "Check the DMV form instructions for Box 12.",
     "Global: all customers on this form.", "Calibrator edits the mapping record; regression-test leased transactions.", "High"),
    (2, "We never fill in the odometer reading on brand-new vehicles. Please leave it blank.",
     "Customer preference vs state rule", "May be a house habit or a real exemption.",
     "Check the state rule: is odometer required or exempt for new vehicles?",
     "If the state exempts it: global conditional rule. If only a preference: per-customer override.",
     "Calibrator adds a condition, or a customer-level override, and logs the reason.", "Medium"),
    (3, "The VIN on page 2 is wrong. It has an O where it should be a 0.", "Data / extraction error (not a mapping)",
     "OCR/extraction misread; VINs never contain I, O or Q.", "Compare to the source document; check the VIN check digit.",
     "Global extraction fix plus a validation rule.",
     "Route to the AI/extraction team; add a VIN validation check. No mapping change.", "High"),
    (4, "This is the old version of the form. The DMV switched to the new one last month.", "Form version change",
     "The form template is stale.", "Confirm on the DMV site; diff old vs new fields.",
     "Global: the form and every mapping on it.",
     "Version the form record, re-map changed fields, re-calibrate; set up DMV form-change monitoring.", "Critical"),
    (5, "The purchase price should include the dealer fees. (A second clerk said the opposite.)",
     "Conflicting feedback", "Ambiguous state definition or inconsistent internal practice.",
     "Check the state's definition of taxable purchase price; ask the customer's admin for the policy.",
     "Global if the state defines it; per-customer only if the state allows either.",
     "Hold the change; escalate to the customer's account owner for one answer; document the decision.", "Medium"),
    (6, "Why is the lienholder section filled in? This vehicle was paid in cash.", "Mapping rule / condition error",
     "Condition 'only fill if financed' is missing, or bad input data.",
     "Check the transaction: does the input data show a lien?",
     "Global rule fix if the condition is wrong; data fix if the input was wrong.",
     "Calibrator adds or fixes the condition; regression-test cash and financed transactions.", "High"),
]

PROCESS = [
    ("1. Capture", "Every comment is logged against a form, field, transaction and customer (structured, not free-text email)."),
    ("2. Classify", "Mapping error / condition error / customer preference / extraction bug / form version / conflicting."),
    ("3. Verify", "Check against the DMV rule or instructions and the source documents before changing anything."),
    ("4. Scope", "Decide global (state rule) vs per-customer override. The default is global only when the state rule supports it."),
    ("5. Change", "Edit the mapping record (or route to AI or forms work) with a reason and a link to the comment."),
    ("6. Test", "Regression-test against past calibrated transactions for that form before publishing."),
    ("7. Close loop", "Reply to the customer, and track repeat-error rate per form as the calibration quality KPI."),
]


def header(ws, row, labels, widths=None):
    for i, label in enumerate(labels, 1):
        c = ws.cell(row=row, column=i, value=label)
        c.font, c.fill = HEAD, HEAD_FILL
        c.alignment = Alignment(wrap_text=True, vertical="center")
    if widths:
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = ws.cell(row=row + 1, column=1)


def title(ws, text, sub):
    ws["A1"], ws["A2"] = text, sub
    ws["A1"].font, ws["A2"].font = TITLE, SUB


def build():
    tx, pipe, market = A.load()
    pipe, alloc = A.allocate_pipeline(pipe, market)
    ranked = A.score(tx, alloc, market)
    _, sens_summary = A.sensitivity(tx, alloc, market)
    cal = A.calendar(ranked, tx)

    wb = Workbook()
    readme = wb.active
    readme.title = "README"
    names = ["Top 10", "Scorecard", "Weights", "Calendar", "Sensitivity", "Pipeline",
             "Pipeline Alloc", "Market Data", "Transactions", "Feedback Process"]
    sheets = {n: wb.create_sheet(n) for n in names}

    # --- Transactions (raw input) ---
    ws = sheets["Transactions"]
    header(ws, 1, ["customer_id", "state", "date", "transaction_type"], [12, 22, 12, 28])
    for r, row in enumerate(tx.itertuples(index=False), 2):
        for c, v in enumerate([int(row.customer_id), row.state, row.date, row.transaction_type], 1):
            ws.cell(row=r, column=c, value=v).font = BLUE
    n_tx_last = len(tx) + 1

    # --- Market Data ---
    ws = sheets["Market Data"]
    header(ws, 1, ["state", "abbr", "FHWA registrations 2023", "New vehicle sales 2025"], [22, 7, 24, 24])
    for r, row in enumerate(market.itertuples(index=False), 2):
        vals = [row.state, row.abbr, int(row.fhwa_registrations_2023),
                None if row.new_vehicle_sales_2025 != row.new_vehicle_sales_2025 else int(row.new_vehicle_sales_2025)]
        for c, v in enumerate(vals, 1):
            cell = ws.cell(row=r, column=c, value=v)
            cell.font = BLUE
            if c > 2:
                cell.number_format = NUM
    ws["F1"], ws["F1"].font = "Sources", BOLD
    notes = [
        "FHWA Highway Statistics 2023, Table MV-1, 'All motor vehicles, Total' column: https://www.fhwa.dot.gov/policyinformation/statistics/2023/pdf/mv1.pdf",
        "2025 new-vehicle sales by state: F&I Tools Full Year 2025 Vehicle Sales Report via https://www.factorywarrantylist.com/car-sales-by-state.html",
        "DC has no 2025 sales figure; its market score uses registrations only.",
        "Caveat: Oklahoma's sales figure (610k) looks high relative to its registrations. Market is only 5% of the score, so it doesn't move the top 10.",
        "Used-vehicle volume by state isn't included; registrations stand in for the total title/registration workload.",
    ]
    for i, n in enumerate(notes, 2):
        ws.cell(row=i, column=6, value=n).font = BLACK
    ws.column_dimensions["F"].width = 110

    # --- Pipeline ---
    ws = sheets["Pipeline"]
    title(ws, "Sales pipeline and Autofill adjustments",
          "Blue = inputs (raw data, haircuts, exclusions). Adjusted value = value x probability x haircut, counted only if the deal includes Autofill.")
    cols = ["deal_id", "account", "segment", "stage", "close_probability", "annual_value_usd", "expected_close",
            "products", "states", "notes", "Includes Autofill?", "Excluded? (1=yes)", "Haircut", "Counted?",
            "Adjusted value ($)", "# states", "Adjustment reason"]
    header(ws, 4, cols, [7, 30, 18, 13, 11, 14, 13, 16, 22, 50, 11, 11, 9, 9, 15, 8, 60])
    for i, d in enumerate(pipe.itertuples(index=False)):
        r = 5 + i
        n_states = 50 if d.states.strip() == "All 50" else len(d.states.split(","))
        raw = [d.deal_id, d.account, d.segment, d.stage, d.prob, int(d.annual_value_usd), d.expected_close,
               d.products, d.states, d.notes if isinstance(d.notes, str) else ""]
        for c, v in enumerate(raw, 1):
            ws.cell(row=r, column=c, value=v).font = BLUE
        ws.cell(row=r, column=5).number_format = PCT
        ws.cell(row=r, column=6).number_format = USD
        ws.cell(row=r, column=11, value=f'=IF(OR(ISNUMBER(SEARCH("Autofill",H{r})),ISNUMBER(SEARCH("Complete",H{r}))),1,0)')
        ws.cell(row=r, column=12, value=1 if d.deal_id in A.EXCLUDED else 0).font = BLUE
        h = ws.cell(row=r, column=13, value=float(d.haircut))
        h.font, h.number_format = BLUE, PCT
        if d.haircut < 1:
            h.fill = YELLOW
        ws.cell(row=r, column=14, value=f"=IF(AND(K{r}=1,L{r}=0,E{r}>0),1,0)")
        ws.cell(row=r, column=15, value=f"=N{r}*F{r}*E{r}*M{r}").number_format = USD
        ws.cell(row=r, column=16, value=n_states).font = BLUE
        reason = d.adjustment_reason or ("Closed Lost: 0% probability" if d.prob == 0 else "")
        ws.cell(row=r, column=17, value=reason).font = BLACK
    p_last = 4 + len(pipe)
    ws.cell(row=p_last + 1, column=14, value="Total").font = BOLD
    t = ws.cell(row=p_last + 1, column=15, value=f"=SUM(O5:O{p_last})")
    t.font, t.number_format = BOLD, USD

    # --- Pipeline Alloc ---
    ws = sheets["Pipeline Alloc"]
    title(ws, "Pipeline allocated to states", "Each deal's adjusted value is split evenly across the states it covers ('All 50' = 50 states).")
    header(ws, 4, ["deal_id", "state", "# states", "Deal adjusted value ($)", "Allocated to state ($)"], [9, 22, 10, 22, 22])
    for i, a in enumerate(alloc.itertuples(index=False)):
        r = 5 + i
        ws.cell(row=r, column=1, value=a.deal_id).font = BLUE
        ws.cell(row=r, column=2, value=a.state).font = BLUE
        ws.cell(row=r, column=3, value=f"=INDEX(Pipeline!$P$5:$P${p_last},MATCH(A{r},Pipeline!$A$5:$A${p_last},0))")
        ws.cell(row=r, column=4, value=f"=INDEX(Pipeline!$O$5:$O${p_last},MATCH(A{r},Pipeline!$A$5:$A${p_last},0))").number_format = USD
        ws.cell(row=r, column=5, value=f"=IF(C{r}=0,0,D{r}/C{r})").number_format = USD
    a_last = 4 + len(alloc)

    # --- Weights ---
    ws = sheets["Weights"]
    title(ws, "Scoring weights and settings", "Yellow = the levers to test in the debrief. Weights must sum to 100%.")
    header(ws, 4, ["Component", "Key", "Weight", "What it measures / why"], [36, 12, 10, 100])
    wrows = [
        ("Existing-customer transaction volume", "volume", "Share of the 200 recent transactions in the state. The strongest traction signal: they are live users who'll give calibration feedback."),
        ("Anchor customer (87) volume", "anchor", "Customer 87 is our biggest account: Audit in 30+ states, 68% of transactions, D01 Autofill expansion. Winning them is the reference story."),
        ("Commitments to existing customers", "commitment", "Signed or explicit asks: D09 Q4 promise (GA/AL/TN), D02 Texas-first (TX; FL/AZ at 80%). Set on the Scorecard, column G."),
        ("Probability-weighted Autofill pipeline", "pipeline", "Autofill deals only, value x probability x haircut, split across states. Secondary to usage."),
        ("Market size", "market", "Average of normalized FHWA registrations and 2025 new-vehicle sales. A tie-breaker only."),
    ]
    for i, (label, key, why) in enumerate(wrows):
        r = 5 + i
        ws.cell(row=r, column=1, value=label).font = BLACK
        ws.cell(row=r, column=2, value=key).font = BLACK
        c = ws.cell(row=r, column=3, value=A.WEIGHTS[key])
        c.font, c.fill, c.number_format = BLUE, YELLOW, PCT
        ws.cell(row=r, column=4, value=why).alignment = WRAP
    ws["A10"], ws["A10"].font = "Total (must be 100%)", BOLD
    ws["C10"], ws["C10"].number_format, ws["C10"].font = "=SUM(C5:C9)", PCT, BOLD
    ws["D10"] = '=IF(ROUND(C10,4)=1,"OK","Weights do not sum to 100%")'
    ws["A11"], ws["C11"] = "Anchor customer_id", int(A.ANCHOR_CUSTOMER)
    ws["A12"], ws["C12"] = "Top N states", A.TOP_N
    for ref in ("C11", "C12"):
        ws[ref].font = BLUE

    # --- Scorecard ---
    ws = sheets["Scorecard"]
    title(ws, "State scorecard (live)", "Score = SUMPRODUCT of weights x components normalized 0-1 (value / max across states). Edit Weights or column G to re-rank.")
    cols = ["State", "Abbr", "Transactions", "New", "Used", "Anchor (87) txns", "Commitment (0-1)", "Commitment basis",
            "Autofill pipeline ($)", "FHWA registrations", "New sales 2025", "Volume (norm)", "Anchor (norm)",
            "Commitment (norm)", "Pipeline (norm)", "Market (norm)", "Score", "Rank", "Top N?", "Rationale"]
    header(ws, 4, cols, [20, 6, 12, 7, 7, 11, 12, 44, 14, 14, 12, 10, 10, 11, 10, 10, 9, 7, 8, 80])
    first, last = 5, 5 + len(ranked) - 1
    rng = lambda col: f"{col}${first}:{col}${last}"
    for i, s in enumerate(ranked.itertuples(index=False)):
        r = first + i
        ws.cell(row=r, column=1, value=s.state).font = BLUE
        ws.cell(row=r, column=2, value=s.abbr).font = BLUE
        ws.cell(row=r, column=3, value=f"=COUNTIF(Transactions!$B$2:$B${n_tx_last},$A{r})")
        ws.cell(row=r, column=4, value=f'=COUNTIFS(Transactions!$B$2:$B${n_tx_last},$A{r},Transactions!$D$2:$D${n_tx_last},"New vehicle transaction")')
        ws.cell(row=r, column=5, value=f'=COUNTIFS(Transactions!$B$2:$B${n_tx_last},$A{r},Transactions!$D$2:$D${n_tx_last},"Used vehicle transaction")')
        ws.cell(row=r, column=6, value=f"=COUNTIFS(Transactions!$B$2:$B${n_tx_last},$A{r},Transactions!$A$2:$A${n_tx_last},Weights!$C$11)")
        g = ws.cell(row=r, column=7, value=float(s.commitment))
        g.font = BLUE
        if s.commitment:
            g.fill = YELLOW
        ws.cell(row=r, column=8, value=s.commitment_note).font = BLACK
        ws.cell(row=r, column=9, value=f"=SUMIF('Pipeline Alloc'!$B$5:$B${a_last},$A{r},'Pipeline Alloc'!$E$5:$E${a_last})").number_format = USD
        ws.cell(row=r, column=10, value=f"=INDEX('Market Data'!$C$2:$C$52,MATCH($A{r},'Market Data'!$A$2:$A$52,0))").number_format = NUM
        ws.cell(row=r, column=11, value=f"=INDEX('Market Data'!$D$2:$D$52,MATCH($A{r},'Market Data'!$A$2:$A$52,0))").number_format = NUM
        ws.cell(row=r, column=12, value=f"=IF(MAX({rng('C')})=0,0,C{r}/MAX({rng('C')}))")
        ws.cell(row=r, column=13, value=f"=IF(MAX({rng('F')})=0,0,F{r}/MAX({rng('F')}))")
        ws.cell(row=r, column=14, value=f"=G{r}")
        ws.cell(row=r, column=15, value=f"=IF(MAX({rng('I')})=0,0,I{r}/MAX({rng('I')}))")
        ws.cell(row=r, column=16, value=f"=IF(K{r}=0,J{r}/MAX({rng('J')}),(J{r}/MAX({rng('J')})+K{r}/MAX({rng('K')}))/2)")
        ws.cell(row=r, column=17, value=f"=Weights!$C$5*L{r}+Weights!$C$6*M{r}+Weights!$C$7*N{r}+Weights!$C$8*O{r}+Weights!$C$9*P{r}").font = BOLD
        ws.cell(row=r, column=18, value=f'=RANK(Q{r},{rng("Q")})+COUNTIFS({rng("Q")},Q{r},{rng("C")},">"&C{r})').font = BOLD
        ws.cell(row=r, column=19, value=f'=IF(R{r}<=Weights!$C$12,"Yes","")')
        ws.cell(row=r, column=20, value=RATIONALE.get(s.state, "")).font = BLACK
        for c in range(12, 18):
            ws.cell(row=r, column=c).number_format = SCORE
        for c in (3, 4, 5, 6):
            ws.cell(row=r, column=c).number_format = NUM
    ws.cell(row=first, column=7).comment = Comment(
        "Commitment scores are judgment inputs. 1.0 = signed or explicit ask from an existing customer; 0.8 = the deal at 80% with pricing agreed. See DECISIONS.md.", "Analyst")

    # --- Top 10 ---
    ws = sheets["Top 10"]
    title(ws, "Top 10 states to calibrate first (traction-first)", "Pulled live from the Scorecard. Change the weights on 'Weights' and this list re-orders.")
    header(ws, 4, ["Rank", "State", "Score", "Transactions", "Anchor (87) txns", "Commitment basis", "Rationale"],
           [7, 18, 9, 13, 14, 48, 90])
    for k in range(1, 11):
        r = 4 + k
        ws.cell(row=r, column=1, value=k).font = BOLD
        m = f"MATCH($A{r},Scorecard!$R${first}:$R${last},0)"
        for c, col, fmt in [(2, "A", None), (3, "Q", SCORE), (4, "C", NUM), (5, "F", NUM), (6, "H", None), (7, "T", None)]:
            cell = ws.cell(row=r, column=c, value=f"=INDEX(Scorecard!${col}${first}:${col}${last},{m})")
            cell.alignment = WRAP
            if fmt:
                cell.number_format = fmt
        ws.row_dimensions[r].height = 32
    ws["A16"], ws["A16"].font = "Share of recent transactions covered by the top 10:", BOLD
    ws["F16"] = f"=SUM(D5:D14)/COUNTA(Transactions!$A$2:$A${n_tx_last})"
    ws["F16"].number_format, ws["F16"].font = PCT, BOLD
    ws["A17"] = f"=\"Anchor customer 87 coverage: \"&TEXT(SUM(E5:E14)/COUNTIF(Transactions!$A$2:$A${n_tx_last},Weights!$C$11),\"0%\")&\" of their transactions\""

    # --- Calendar ---
    ws = sheets["Calendar"]
    title(ws, "Calibration calendar: 1 person, 1 form per day",
          "Snapshot of the base-weight order. Wave 1 = the main form in each top-10 state (TX gets both forms, per D02). Wave 2 = the remaining forms by volume.")
    header(ws, 4, ["Day", "Wave", "State", "Form", "Recent volume", "Cumulative % of transactions covered"], [6, 6, 18, 28, 14, 20])
    for i, f in enumerate(cal.itertuples(index=False)):
        r = 5 + i
        ws.cell(row=r, column=1, value=int(f.day))
        ws.cell(row=r, column=2, value=int(f.wave))
        ws.cell(row=r, column=3, value=f.state).font = BLUE
        ws.cell(row=r, column=4, value=f.form).font = BLUE
        ws.cell(row=r, column=5, value=f"=COUNTIFS(Transactions!$B$2:$B${n_tx_last},C{r},Transactions!$D$2:$D${n_tx_last},D{r})").number_format = NUM
        ws.cell(row=r, column=6, value=f"=SUM($E$5:E{r})/COUNTA(Transactions!$A$2:$A${n_tx_last})").number_format = PCT
    note_r = 6 + len(cal)
    ws.cell(row=note_r, column=1, value="Assumption: 2 forms per state (new-vehicle title and used/transfer title). Replace with the real form list per state before committing.").font = SUB

    # --- Sensitivity ---
    ws = sheets["Sensitivity"]
    title(ws, "Sensitivity: does the top 10 hold if the weights move?",
          "Snapshot from analysis.py: each weight is shifted +/-10pp (the others rescaled) = 11 scenarios including the base.")
    header(ws, 4, ["State", "Times in top 10", "Scenarios", "Best rank", "Worst rank"], [20, 15, 11, 10, 11])
    for i, (state, s) in enumerate(sens_summary.iterrows()):
        r = 5 + i
        for c, v in enumerate([state, int(s.times_in_top10), int(s.scenarios), int(s.best_rank), int(s.worst_rank)], 1):
            ws.cell(row=r, column=c, value=v).font = BLUE

    # --- Feedback Process (Part 2) ---
    ws = sheets["Feedback Process"]
    title(ws, "Part 2: Customer feedback -> form and mapping changes", "Process steps, then a triage of the six example comments.")
    header(ws, 4, ["Step", "What happens"], [16, 110])
    ws.freeze_panes = None
    for i, (step, what) in enumerate(PROCESS):
        ws.cell(row=5 + i, column=1, value=step).font = BOLD
        ws.cell(row=5 + i, column=2, value=what).alignment = WRAP
    start = 5 + len(PROCESS) + 2
    fb_cols = ["#", "Comment", "Category", "Likely root cause", "How to verify", "Scope", "Action / owner", "Priority"]
    for i, lab in enumerate(fb_cols, 1):
        c = ws.cell(row=start, column=i, value=lab)
        c.font, c.fill = HEAD, HEAD_FILL
    for col, w in zip("CDEFGH", [28, 34, 38, 38, 48, 10]):
        ws.column_dimensions[col].width = w
    ws.column_dimensions["B"].width = 50
    ws.column_dimensions["A"].width = 16
    for i, row in enumerate(FEEDBACK):
        r = start + 1 + i
        for c, v in enumerate(row, 1):
            ws.cell(row=r, column=c, value=v).alignment = WRAP
        ws.row_dimensions[r].height = 60

    # --- README ---
    ws = readme
    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 110
    title(ws, "Fairway Autofill: which states to calibrate first", "Business Operations case study. Traction-first prioritization.")
    lines = [
        ("Thesis", "Autofill is a new product, so the goal of the first ~20 calibration days is traction: live usage and referenceable customers. So we rank states by where our existing customers, especially our biggest account (customer 87), already submit paperwork, then by commitments we've made. Pipeline $ and market size only break ties."),
        ("How to use", "Change the yellow cells on 'Weights' (or the commitment scores in Scorecard column G). 'Scorecard' and 'Top 10' recalculate."),
        ("Colour legend", "Blue text = hard-coded input or raw data. Black = formula. Yellow fill = a key judgment assumption to debate."),
        ("Tabs", "Top 10 | Scorecard | Weights | Calendar | Sensitivity | Pipeline | Pipeline Alloc | Market Data | Transactions | Feedback Process"),
        ("Data", "transactions.csv: 200 transactions, Sep 24-28 2026, 4 customers. sales_pipeline.csv: 20 deals. Market data: FHWA MV-1 2023 and 2025 new-vehicle sales (sources on the Market Data tab)."),
        ("Key caveats", "Only 5 days of transactions; customer 87 is 68% of the sample. The number of forms per state is assumed to be 2. Rep probabilities are uncalibrated. Full reasoning: DECISIONS.md in the repo."),
    ]
    for i, (k, v) in enumerate(lines, 4):
        ws.cell(row=i, column=1, value=k).font = BOLD
        ws.cell(row=i, column=2, value=v).alignment = WRAP
        ws.row_dimensions[i].height = 45

    for sheet in wb.worksheets:
        for row in sheet.iter_rows():
            for cell in row:
                if cell.font and cell.font.name != FONT:
                    f = cell.font
                    cell.font = Font(name=FONT, bold=f.bold, italic=f.italic, color=f.color, size=f.size)
    wb.calculation.fullCalcOnLoad = True
    out = A.OUT / "Fairway_State_Prioritization.xlsx"
    A.OUT.mkdir(exist_ok=True)
    wb.save(out)
    print("wrote", out)


if __name__ == "__main__":
    build()
