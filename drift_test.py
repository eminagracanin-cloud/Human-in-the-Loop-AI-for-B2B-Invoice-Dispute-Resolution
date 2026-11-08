# Drift test: a known invoicing rule changes, and the pipeline has to cope.

#From the drift date, existing agreements get an announced 5 percent price rise in the
#CRM, the ERP and the invoices, while the billing history keeps the old prices
#(see DATASETS in generate_cases.py). Makes three runs of the v2 rules, by invoice month:
  #control   synthetic_data (no drift)
  #drift     synthetic_data_price increase, system not told in the pipeline
  #uplift    synthetic_data_drift, uplift documented in DOCUMENTED_UPLIFTS

#Usage: python drift_test.py
#(create the data first: python generate_cases.py makes synthetic_data_drift too)

import os

import matplotlib.pyplot as plt

from evaluate import load_truths, score_folder, make_config, save_rows
from generate_cases import DRIFT_DATE, DRIFT_PRICE_RISE
from pipeline.data import load


RESULTS_FOLDER = "results"      # where the CSVs and the chart go


def month_of(row):
    return row["period"][:7]            # "2025-07"


def tally(rows):
    """n, exact and over-escalation counts per month, plus before/after the drift date."""
    months = {}
    sides = {"before": [0, 0, 0], "after": [0, 0, 0]}
    for row in rows:
        month = month_of(row)
        if month not in months:
            months[month] = [0, 0, 0]
        side = "before"
        if row["period"] >= DRIFT_DATE.isoformat():
            side = "after"
        for counts in (months[month], sides[side]):
            counts[0] += 1
            if row["category"] == "exact":
                counts[1] += 1
            if row["category"] == "over_escalation":
                counts[2] += 1
    return months, sides


def percent(part, whole):
    if whole == 0:
        return 0.0
    return 100.0 * part / whole


def run_one(folder, config):
    data = load(folder)
    truths = load_truths(folder)
    return score_folder(data, truths, config)


def main():
    os.makedirs(RESULTS_FOLDER, exist_ok=True)

    plain = make_config("v2")
    documented = make_config("v2")
    documented["documented_uplifts"] = [(DRIFT_DATE.isoformat(), 1 + DRIFT_PRICE_RISE)]

    runs = [("no price increase (control)", run_one("synthetic_data", plain)),
            ("price increase, system not told", run_one("synthetic_data_drift", plain)),
            ("price increase, system told", run_one("synthetic_data_drift", documented))]

    tallies = []
    for label, rows in runs:
        months, sides = tally(rows)
        tallies.append((label, months, sides))

    print(f"DRIFT TEST (v2 rules): {DRIFT_PRICE_RISE * 100:.0f}% price rise on existing agreements "
          f"from {DRIFT_DATE}")
    print("Exact accuracy and over-escalation rate (over-escalated cases / all cases).")

    print()
    print(f"  {'run':32s}{'period':>8s}{'n':>5s}{'exact%':>8s}{'over%':>7s}")
    summary_csv = []
    for label, months, sides in tallies:
        for side in ["before", "after"]:
            n, exact, over = sides[side]
            print(f"  {label:32s}{side:>8s}{n:5d}{percent(exact, n):7.1f}%{percent(over, n):6.1f}%")
            summary_csv.append({"run": label, "period": side, "n": n,
                                "exact_pct": round(percent(exact, n), 1),
                                "over_escalation_pct": round(percent(over, n), 1)})

    print()
    print("Monthly (invoice period); '<' = before the drift date, '>' = from it")
    header = f"  {'month':9s}"
    for label, months, sides in tallies:
        header += f"{label[:24]:>26s}"
    print(header)
    print(f"  {'':9s}" + f"{'n  exact%  over%':>26s}" * len(tallies))
    month_names = sorted(tallies[0][1].keys())
    monthly_csv = []
    for month in month_names:
        marker = "<"
        if month + "-01" >= DRIFT_DATE.isoformat():
            marker = ">"
        line = f"  {month} {marker} "
        for label, months, sides in tallies:
            n, exact, over = months[month]
            line += f"{n:6d}{percent(exact, n):8.1f}%{percent(over, n):8.1f}%"
            monthly_csv.append({"run": label, "month": month, "n": n,
                                "exact_pct": round(percent(exact, n), 1),
                                "over_escalation_pct": round(percent(over, n), 1)})
        print(line)

    save_rows(summary_csv, os.path.join(RESULTS_FOLDER, "drift_summary.csv"))
    save_rows(monthly_csv, os.path.join(RESULTS_FOLDER, "drift_monthly.csv"))

    # Chart: monthly exact accuracy across the drift.
    figure, axis = plt.subplots(figsize=(6, 3.4))
    styles = [("#7a7a7a", "--"), ("#c0392b", "-"), ("#1f77b4", "-")]
    for i in range(len(tallies)):
        label, months, sides = tallies[i]
        values = []
        for month in month_names:
            n, exact, over = months[month]
            values.append(percent(exact, n))
        axis.plot(month_names, values, marker="o", color=styles[i][0],
                  linestyle=styles[i][1], label=label)
    drift_month = DRIFT_DATE.isoformat()[:7]
    axis.axvline(month_names.index(drift_month) - 0.5, color="black", linewidth=1)
    axis.text(month_names.index(drift_month) - 0.4, 3, "price increase starts", fontsize=9)
    axis.set_ylim(0, 100)
    axis.set_ylabel("exact accuracy (%)")
    axis.set_xlabel("invoice month")
    axis.legend(loc="lower left", fontsize=9)
    plt.setp(axis.get_xticklabels(), rotation=45, ha="right")
    figure.tight_layout()
    chart_path = os.path.join(RESULTS_FOLDER, "drift_monthly_accuracy.png")
    figure.savefig(chart_path, dpi=150)
    print()
    print(f"Saved {chart_path}, drift_summary.csv, drift_monthly.csv in {RESULTS_FOLDER}/")


if __name__ == "__main__":
    main()
