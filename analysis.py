"""Fairway Autofill state prioritization (traction-first).

Reads Data/*.csv and writes output/*.csv. See DECISIONS.md for the reasoning
behind every weight, haircut and commitment score used here.
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent
DATA = ROOT / "Data"
OUT = ROOT / "output"

ANCHOR_CUSTOMER = "87"  # our largest existing customer (Audit in 30+ states)
TOP_N = 10
TX_TYPES = ["New vehicle transaction", "Used vehicle transaction"]

# Component weights (must sum to 1). Traction-first: real usage dominates.
WEIGHTS = {
    "volume": 0.45,      # existing-customer transactions in the state
    "anchor": 0.20,      # customer 87's transactions in the state
    "commitment": 0.20,  # signed / explicit asks from existing customers
    "pipeline": 0.10,    # probability-weighted Autofill pipeline $
    "market": 0.05,      # FHWA registrations + 2025 new-vehicle sales
}

# Explicit commitments to customers we already have (0-1).
COMMITMENTS = {
    "Texas": (1.0, "D02: existing customers 110/121, pricing agreed, 'wants Texas live first'"),
    "Georgia": (1.0, "D09: Closed Won, Autofill promised for Q4"),
    "Alabama": (1.0, "D09: Closed Won, Autofill promised for Q4"),
    "Tennessee": (1.0, "D09: Closed Won, Autofill promised for Q4"),
    "Florida": (0.8, "D02: existing customer 121, Negotiation at 80%"),
    "Arizona": (0.8, "D02: Negotiation at 80%"),
}

# Deal-level adjustments on top of the rep's probability.
HAIRCUTS = {
    "D06": (0.25, "Expected close 2026-06-30 already passed; stuck in legal since May"),
    "D05": (0.50, "Discovery stage; amount is the rep's estimate after one call"),
    "D08": (0.50, "Conditional on a state fee bill passing next session"),
}
EXCLUDED = {"D10": "Audit only; creates no Autofill calibration need"}


def load():
    tx = pd.read_csv(DATA / "transactions.csv", dtype={"customer_id": str})
    pipe = pd.read_csv(DATA / "sales_pipeline.csv")
    market = pd.read_csv(DATA / "market_data.csv")
    return tx, pipe, market


def allocate_pipeline(pipe, market):
    """Spread each deal's adjusted value evenly across the states it covers."""
    abbr_to_state = dict(zip(market.abbr, market.state))
    fifty = [s for s in market.state if s != "District of Columbia"]
    pipe = pipe.copy()
    pipe["prob"] = pipe.close_probability.str.rstrip("%").astype(float) / 100
    pipe["includes_autofill"] = pipe.products.str.contains("Autofill|Complete")
    pipe["haircut"] = pipe.deal_id.map(lambda d: HAIRCUTS.get(d, (1.0, ""))[0])
    pipe["adjustment_reason"] = pipe.deal_id.map(
        lambda d: EXCLUDED.get(d) or HAIRCUTS.get(d, (None, ""))[1])
    pipe["counted"] = pipe.includes_autofill & ~pipe.deal_id.isin(EXCLUDED) & (pipe.prob > 0)
    pipe["adj_value"] = (pipe.annual_value_usd * pipe.prob * pipe.haircut).where(pipe.counted, 0.0)

    rows = []
    for _, d in pipe.iterrows():
        states = fifty if d.states.strip() == "All 50" else [
            abbr_to_state[a.strip()] for a in d.states.split(",")]
        for s in states:
            rows.append({"deal_id": d.deal_id, "state": s, "n_states": len(states),
                         "alloc_value": d.adj_value / len(states)})
    return pipe, pd.DataFrame(rows)


def score(tx, alloc, market, weights=WEIGHTS):
    df = market[["state", "abbr", "fhwa_registrations_2023", "new_vehicle_sales_2025"]].copy()
    df["transactions"] = df.state.map(tx.state.value_counts()).fillna(0).astype(int)
    df["anchor_transactions"] = df.state.map(
        tx[tx.customer_id == ANCHOR_CUSTOMER].state.value_counts()).fillna(0).astype(int)
    for t in TX_TYPES:
        key = "new" if t.startswith("New") else "used"
        df[f"{key}_transactions"] = df.state.map(
            tx[tx.transaction_type == t].state.value_counts()).fillna(0).astype(int)
    df["commitment"] = df.state.map(lambda s: COMMITMENTS.get(s, (0.0, ""))[0])
    df["commitment_note"] = df.state.map(lambda s: COMMITMENTS.get(s, (0.0, ""))[1])
    df["pipeline_usd"] = df.state.map(alloc.groupby("state").alloc_value.sum()).fillna(0)

    norm = lambda c: c / c.max()
    df["n_volume"] = norm(df.transactions)
    df["n_anchor"] = norm(df.anchor_transactions)
    df["n_commitment"] = df.commitment
    df["n_pipeline"] = norm(df.pipeline_usd)
    # DC has no sales figure: fall back to registrations only.
    reg, sales = norm(df.fhwa_registrations_2023), norm(df.new_vehicle_sales_2025)
    df["n_market"] = ((reg + sales) / 2).fillna(reg)

    df["score"] = sum(weights[k] * df[f"n_{k}"] for k in weights)
    df = df.sort_values(["score", "transactions"], ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1
    return df


def sensitivity(tx, alloc, market):
    """Shift each weight +/-10pp (others rescaled) and count top-10 appearances."""
    scenarios = {"base": WEIGHTS}
    for k in WEIGHTS:
        for delta in (-0.10, 0.10):
            w = dict(WEIGHTS)
            w[k] = max(0.0, w[k] + delta)
            rest = sum(v for j, v in WEIGHTS.items() if j != k)
            for j in WEIGHTS:
                if j != k:
                    w[j] = WEIGHTS[j] * (1 - w[k]) / rest
            scenarios[f"{k}{delta:+.0%}"] = w
    rows = []
    for name, w in scenarios.items():
        top = score(tx, alloc, market, w).head(TOP_N)
        rows += [{"scenario": name, "state": s, "rank": r} for s, r in zip(top.state, top["rank"])]
    res = pd.DataFrame(rows)
    summary = (res.groupby("state").agg(times_in_top10=("scenario", "count"),
                                        best_rank=("rank", "min"), worst_rank=("rank", "max"))
               .sort_values(["times_in_top10", "best_rank"], ascending=[False, True]))
    summary["scenarios"] = len(scenarios)
    return res, summary


def calendar(ranked, tx):
    """One form per day. Wave 1: each top state's main form (TX gets both,
    per D02's Texas-first ask). Wave 2: the remaining forms by volume."""
    top = ranked.head(TOP_N)
    forms = []
    for _, r in top.iterrows():
        for t in TX_TYPES:
            key = "new" if t.startswith("New") else "used"
            forms.append({"state": r.state, "state_rank": r["rank"], "form": t,
                          "volume": int(r[f"{key}_transactions"])})
    forms = pd.DataFrame(forms)
    forms["is_primary"] = forms.groupby("state").volume.rank(method="first", ascending=False) == 1
    forms.loc[forms.state == "Texas", "is_primary"] = True
    wave1 = forms[forms.is_primary].sort_values(["state_rank", "volume"], ascending=[True, False])
    wave2 = forms[~forms.is_primary].sort_values(["volume", "state_rank"], ascending=[False, True])
    cal = pd.concat([wave1.assign(wave=1), wave2.assign(wave=2)]).reset_index(drop=True)
    cal.insert(0, "day", cal.index + 1)
    cal["cum_share_of_transactions"] = cal.volume.cumsum() / len(tx)
    return cal.drop(columns="is_primary")


def main():
    OUT.mkdir(exist_ok=True)
    tx, pipe, market = load()
    assert len(tx) == 200 and len(pipe) == 20, "unexpected input sizes"
    pipe, alloc = allocate_pipeline(pipe, market)
    ranked = score(tx, alloc, market)
    sens, sens_summary = sensitivity(tx, alloc, market)
    cal = calendar(ranked, tx)

    pipe.to_csv(OUT / "pipeline_adjusted.csv", index=False)
    alloc.to_csv(OUT / "pipeline_allocation.csv", index=False)
    ranked.to_csv(OUT / "state_scorecard.csv", index=False)
    sens_summary.to_csv(OUT / "sensitivity.csv")
    cal.to_csv(OUT / "calibration_calendar.csv", index=False)

    cols = ["rank", "state", "transactions", "anchor_transactions", "commitment",
            "pipeline_usd", "n_market", "score"]
    print(ranked[cols].head(15).to_string(index=False, float_format=lambda x: f"{x:,.3f}"))
    print("\nSensitivity (times in top 10 of", len(sens.scenario.unique()), "scenarios):")
    print(sens_summary.head(14).to_string())
    print("\nCalendar:")
    print(cal.to_string(index=False))
    print("\nDeals not counted / adjusted:")
    print(pipe.loc[~pipe.counted | (pipe.haircut < 1),
                   ["deal_id", "account", "stage", "counted", "haircut", "adjustment_reason"]].to_string(index=False))


if __name__ == "__main__":
    main()
