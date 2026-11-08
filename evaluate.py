"""Scores the pipeline against the ground truth: baseline rules versus v2 rules,
on each data folder, with breakdowns and a sensitivity table. CSVs go to results/.
Usage: python evaluate.py   (the folders and the rule versions are set below)
"""
import os

import pandas as pd

from pipeline.data import load
from pipeline.run_pipeline import run_all
from pipeline.settings import CREDIT_TOLERANCE, default_config

# What to run: the data folders, the rule versions, where the CSVs go, and whether
# to skip the sensitivity table.
DATA_FOLDERS = ["synthetic_data", "synthetic_data_clean"]
VERSIONS = ["baseline", "v2"]
RESULTS_FOLDER = "results"
SKIP_SENSITIVITY = False

CREDIT = "credit_system_error"
ESCALATE = "escalate_to_sales_rep"
NO_FAULT = "no_fault"

# Every case lands in exactly one of these.
CATEGORIES = ["exact", "safe_escalation", "false_credit", "over_escalation",
              "missed_error", "credit_detail_wrong"]

# Breakdowns: (name in the output, column of the per-case rows).
DIMENSIONS = [("messiness tag", "messiness"), ("order type", "order_type"),
              ("dispute type", "dispute_type"), ("cause class", "cause_class")]

# The sensitivity table: what an invoice is compared with, and the price tolerance.
SENSITIVITY_REFERENCES = ["median", "most_recent"]
SENSITIVITY_TOLERANCES = [0.0, 0.005, 0.01]


def predicted_credit(result):
    return result["stage3"]["credit_amount"], result["stage3"]["credit_invoice"]


def classify(expected, predicted, ambiguous, credit_ok, invoice_ok):
    if predicted == expected:
        if credit_ok and invoice_ok:
            return "exact"
        return "credit_detail_wrong"            # right outcome, wrong money
    # The data cannot settle an ambiguous case, so asking the rep is safe.
    if ambiguous == 1 and predicted == ESCALATE:
        return "safe_escalation"
    # Credit proposed where none is owed, or where a human should decide.
    if predicted == CREDIT:
        return "false_credit"
    if predicted == ESCALATE and expected == NO_FAULT:
        return "over_escalation"
    # Either no fault was found (but there is one), or a provable system
    # error was handed to a rep instead of being credited.
    return "missed_error"


def invoice_pair(invoice_id, data):
    """Both invoices of a duplicate pair: same customer, product and period."""
    invoices = data["invoices"]
    row = invoices[invoices["invoice_id"] == invoice_id].iloc[0]
    same = invoices[(invoices["customer_id"] == row["customer_id"])
                    & (invoices["product_id"] == row["product_id"])
                    & (invoices["period_start"] == row["period_start"])]
    return list(same["invoice_id"])


def invoice_period(invoice_id, data):
    invoices = data["invoices"]
    row = invoices[invoices["invoice_id"] == invoice_id].iloc[0]
    return str(row["period_start"].date())


def score_case(truth, result, data):
    expected = truth["expected_pipeline_outcome"]
    predicted = result["stage3"]["outcome"]
    ambiguous = 0
    if "ambiguous" in truth:
        ambiguous = int(truth["ambiguous"])

    messiness = "clean"
    if "messiness" in truth and truth["messiness"] != "":
        messiness = truth["messiness"]
    order_type = "unknown"
    if "order_type" in truth:
        order_type = truth["order_type"]

    # Credit checks only make sense when a credit is both owed and proposed.
    credit_ok = True
    invoice_ok = True
    pred_amount, pred_invoice = predicted_credit(result)
    if expected == CREDIT and predicted == CREDIT:
        credit_ok = abs(pred_amount - float(truth["correct_credit"])) <= CREDIT_TOLERANCE
        # For duplicates the right invoice matters, not only the amount.
        if truth["dispute_type"] == "duplicate_charge":
            accepted = [truth["credit_invoice_id"]]
            if messiness == "start_tie":
                # Practitioners credit and close one of the two agreements and
                # keep the other, so either invoice is a correct credit.
                accepted = invoice_pair(truth["credit_invoice_id"], data)
            invoice_ok = pred_invoice in accepted

    category = classify(expected, predicted, ambiguous, credit_ok, invoice_ok)

    found = result["stage2"]["evidence"]
    return {
        "ticket_id": truth["ticket_id"], "invoice_id": truth["invoice_id"],
        "period": invoice_period(truth["invoice_id"], data),
        "dispute_type": truth["dispute_type"], "cause_class": truth["cause_class"],
        "order_type": order_type, "root_cause": truth["root_cause"],
        "messiness": messiness, "ambiguous": ambiguous,
        "expected_outcome": expected, "predicted_outcome": predicted,
        "category": category, "rule_fired": result["stage3"]["rule"],
        "correct_credit": truth["correct_credit"], "predicted_credit": pred_amount,
        "credit_amount_ok": credit_ok,
        "expected_credit_invoice": truth["credit_invoice_id"],
        "predicted_credit_invoice": pred_invoice, "credited_invoice_ok": invoice_ok,
        "escalate_to": result["stage3"]["escalate_to"],
        "note": result["stage3"]["note"],
        "start_date_tie": found.get("start_date_tie", False),
    }


def load_truths(folder):
    table = pd.read_csv(os.path.join(folder, "ground_truth.csv"))
    table = table.fillna("")            # empty cells are "", not NaN
    return table.to_dict("records")


def score_folder(data, truths, config):
    """Runs the pipeline on every disputed invoice and scores each case."""
    invoice_ids = []
    for truth in truths:
        invoice_ids.append(truth["invoice_id"])
    results = run_all(invoice_ids, data, config)
    rows = []
    for i in range(len(truths)):
        rows.append(score_case(truths[i], results[i], data))
    return rows


# ------------------------------------------------------------------- counting

def new_counts():
    counts = {"n": 0}
    for category in CATEGORIES:
        counts[category] = 0
    return counts


def add_count(table, group, category):
    if group not in table:
        table[group] = new_counts()
    table[group]["n"] += 1
    table[group][category] += 1


def count_rows(rows):
    totals = new_counts()
    for row in rows:
        totals["n"] += 1
        totals[row["category"]] += 1
    return totals


def count_by(rows, column):
    table = {}
    for row in rows:
        add_count(table, row[column], row["category"])
    return table


def automation_counts(rows):
    """Cases the pipeline settles by itself (credit or no fault, no escalation),
    and how many of those are exactly right."""
    resolved = 0
    correct = 0
    for row in rows:
        if row["predicted_outcome"] != ESCALATE:
            resolved += 1
            if row["category"] == "exact":
                correct += 1
    return {"n": len(rows), "resolved": resolved, "correct": correct,
            "escalated": len(rows) - resolved}


def exact_percent(counts):
    return 100.0 * counts["exact"] / counts["n"]


def sorted_groups(table):
    groups = sorted(table.keys())
    if "clean" in groups:
        others = []
        for group in groups:
            if group != "clean":
                others.append(group)
        groups = ["clean"] + others
    return groups


# ------------------------------------------------------------------- printing

COLUMNS = (f"{'n':>5s}{'exact':>7s}{'exact%':>8s}{'safe':>6s}{'f.cred':>8s}"
           f"{'over':>6s}{'missed':>8s}{'detail':>8s}")


def counts_text(c):
    return (f"{c['n']:5d}{c['exact']:7d}{exact_percent(c):7.1f}%{c['safe_escalation']:6d}"
            f"{c['false_credit']:8d}{c['over_escalation']:6d}{c['missed_error']:8d}"
            f"{c['credit_detail_wrong']:8d}")


def print_summary(summary_rows):
    print()
    print("SUMMARY: baseline rules versus v2 rules")
    print(f"  {'data':22s}{'rules':>10s}{COLUMNS}")
    for item in summary_rows:
        print(f"  {item['data']:22s}{item['rules']:>10s}{counts_text(item['counts'])}")


def print_automation(rows):
    print()
    print("AUTOMATION: cases resolved without escalating (credit or no fault), and how many are correct")
    print(f"  {'data':22s}{'rules':>10s}{'n':>5s}{'resolved':>10s}{'resolved%':>11s}"
          f"{'correct':>9s}{'correct%':>10s}{'escalated':>11s}")
    for item in rows:
        print(f"  {item['data']:22s}{item['rules']:>10s}{item['n']:5d}{item['resolved']:10d}"
              f"{item['resolved_pct']:10.1f}%{item['correct']:9d}{item['correct_pct']:9.1f}%"
              f"{item['escalated']:11d}")


def print_breakdown(folder, dimension_name, tables):
    """tables maps a rules version to its {group: counts} table."""
    print()
    print(f"{folder}: by {dimension_name}")
    print(f"  {'':22s}{'rules':>10s}{COLUMNS}")
    first_version = list(tables.keys())[0]
    for group in sorted_groups(tables[first_version]):
        for version in tables:
            if group in tables[version]:
                print(f"  {group:22s}{version:>10s}{counts_text(tables[version][group])}")


def print_sensitivity(rows):
    print()
    print("SENSITIVITY: history reference and price tolerance")
    print(f"  {'data':22s}{'rules':>10s}{'reference':>13s}{'tolerance':>11s}{COLUMNS}")
    for item in rows:
        print(f"  {item['data']:22s}{item['rules']:>10s}{item['reference']:>13s}"
              f"{item['tolerance'] * 100:10.1f}%{counts_text(item['counts'])}")


# ----------------------------------------------------------------- saving CSVs

def save_rows(rows, path):
    pd.DataFrame(rows).to_csv(path, index=False)


def counts_columns(counts):
    """The counts as CSV columns."""
    columns = {"n": counts["n"], "exact": counts["exact"],
               "exact_pct": round(exact_percent(counts), 1)}
    for category in CATEGORIES:
        if category != "exact":
            columns[category] = counts[category]
    return columns


def make_config(version, reference=None, tolerance=None):
    config = default_config()
    config["rules_version"] = version
    if reference is not None:
        config["history_reference"] = reference
    if tolerance is not None:
        config["price_tolerance"] = tolerance
    return config


# ------------------------------------------------------------------------ main

def main():
    os.makedirs(RESULTS_FOLDER, exist_ok=True)

    summary_rows = []
    summary_csv = []
    automation_csv = []
    breakdown_csv = []
    breakdown_tables = {}       # (folder, dimension) -> {version: table}

    for folder in DATA_FOLDERS:
        name = folder
        data = load(folder)
        truths = load_truths(folder)
        for version in VERSIONS:
            rows = score_folder(data, truths, make_config(version))
            save_rows(rows, os.path.join(RESULTS_FOLDER, f"cases_{version}_{name}.csv"))

            counts = count_rows(rows)
            summary_rows.append({"data": name, "rules": version, "counts": counts})
            line = {"data": name, "rules": version}
            line.update(counts_columns(counts))
            summary_csv.append(line)

            auto = automation_counts(rows)
            automation_csv.append({
                "data": name, "rules": version, "n": auto["n"],
                "resolved": auto["resolved"],
                "resolved_pct": round(100.0 * auto["resolved"] / auto["n"], 1),
                "correct": auto["correct"],
                "correct_pct": round(100.0 * auto["correct"] / auto["resolved"], 1),
                "escalated": auto["escalated"]})

            for dimension_name, column in DIMENSIONS:
                table = count_by(rows, column)
                key = (name, dimension_name)
                if key not in breakdown_tables:
                    breakdown_tables[key] = {}
                breakdown_tables[key][version] = table
                for group in sorted_groups(table):
                    line = {"data": name, "rules": version,
                            "dimension": dimension_name, "group": group}
                    line.update(counts_columns(table[group]))
                    breakdown_csv.append(line)

    print_summary(summary_rows)
    print_automation(automation_csv)
    for key in breakdown_tables:
        print_breakdown(key[0], key[1], breakdown_tables[key])

    save_rows(summary_csv, os.path.join(RESULTS_FOLDER, "summary.csv"))
    save_rows(breakdown_csv, os.path.join(RESULTS_FOLDER, "breakdown.csv"))
    save_rows(automation_csv, os.path.join(RESULTS_FOLDER, "automation.csv"))

    if not SKIP_SENSITIVITY:
        sensitivity_rows = []
        sensitivity_csv = []
        for folder in DATA_FOLDERS:
            name = folder
            data = load(folder)
            truths = load_truths(folder)
            for version in VERSIONS:
                for reference in SENSITIVITY_REFERENCES:
                    for tolerance in SENSITIVITY_TOLERANCES:
                        rows = score_folder(data, truths, make_config(version, reference, tolerance))
                        counts = count_rows(rows)
                        sensitivity_rows.append({"data": name, "rules": version,
                                                 "reference": reference,
                                                 "tolerance": tolerance, "counts": counts})
                        line = {"data": name, "rules": version, "history_reference": reference,
                                "price_tolerance": tolerance}
                        line.update(counts_columns(counts))
                        sensitivity_csv.append(line)
        print_sensitivity(sensitivity_rows)
        save_rows(sensitivity_csv, os.path.join(RESULTS_FOLDER, "sensitivity.csv"))

    print()
    print("Columns: exact, safe = safe escalation (ambiguous case sent to the rep, scored")
    print("separately), f.cred = false credit, over = over-escalation, missed = missed error,")
    print("detail = credit detail wrong (right outcome, wrong amount or credited invoice)")
    print(f"CSVs saved in {RESULTS_FOLDER}/: summary, automation, breakdown, sensitivity, cases_<rules>_<data>")


if __name__ == "__main__":
    main()
