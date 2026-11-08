"Stage 2 - History check: compares the invoice with earlier billing and looks for a second billing agreement for the same thing. Reports flags, never decides."

import numpy as np

from pipeline.settings import QTY_TOLERANCE, TIE_SEED, default_config


def start_date_of(agreement_id, agreements):
    row = agreements[agreements["agreement_id"] == agreement_id].iloc[0]
    return row["start_date"]


def uplift_factor(period_start, documented_uplifts):
    period_text = str(period_start.date())          # "YYYY-MM-DD" compares in date order
    factor = 1.0
    for effective_date, uplift in documented_uplifts:
        if period_text >= effective_date:
            factor = factor * uplift
    return factor


def check_past_billing(row, history, flags, evidence, config):
    past = history[(history["customer_id"] == row["customer_id"])
                   & (history["product_id"] == row["product_id"])
                   & (history["period_start"] < row["period_start"])]

    if len(past) == 0:
        flags.append("no_history")
        return

    if config["history_reference"] == "most_recent":
        latest = past.sort_values("period_start").iloc[-1]
        hist_price = float(latest["unit_price"])
        hist_qty = float(latest["qty"])
    else:
        hist_price = float(past["unit_price"].median())
        hist_qty = float(past["qty"].median())

    factor = uplift_factor(row["period_start"], config["documented_uplifts"])
    expected_price = hist_price * factor
    price_dev = (row["unit_price"] - expected_price) / expected_price
    evidence["history_price"] = hist_price
    evidence["history_qty"] = hist_qty
    if factor != 1.0:
        evidence["documented_uplift"] = factor
    evidence["price_deviation_pct"] = round(100 * float(price_dev), 1)
    if abs(price_dev) > config["price_tolerance"]:
        flags.append("price_differs_from_history")
    if abs(row["qty"] - hist_qty) > QTY_TOLERANCE:
        flags.append("qty_differs_from_history")


def check_second_agreement(row, invoices, agreements, flags, evidence, tie_rng):
    same_thing = invoices[(invoices["customer_id"] == row["customer_id"])
                          & (invoices["product_id"] == row["product_id"])
                          & (invoices["period_start"] == row["period_start"])
                          & (invoices["invoice_id"] != row["invoice_id"])
                          & (invoices["agreement_id"] != row["agreement_id"])]
    if len(same_thing) == 0:
        return

    other = same_thing.iloc[0]      # the data has exactly one twin invoice
    row_start = start_date_of(row["agreement_id"], agreements)
    other_start = start_date_of(other["agreement_id"], agreements)

    tie = row_start == other_start
    if tie:
        # Same start date: the rule cannot decide. Pick at random, never by
        # invoice id or row order, which would quietly leak the answer.
        row_is_legit = tie_rng.random() < 0.5
    else:
        row_is_legit = row_start < other_start

    if row_is_legit:
        legit, legit_start, dup, dup_start = row, row_start, other, other_start
    else:
        legit, legit_start, dup, dup_start = other, other_start, row, row_start

    flags.append("duplicate_candidate")
    evidence["legit_agreement"] = legit["agreement_id"]
    evidence["legit_start_date"] = str(legit_start.date())
    evidence["duplicate_agreement"] = dup["agreement_id"]
    evidence["duplicate_start_date"] = str(dup_start.date())
    evidence["start_date_tie"] = bool(tie)
    evidence["duplicate_invoice"] = dup["invoice_id"]
    evidence["duplicate_amount"] = float(dup["amount"])
    # Invoice order can disagree with start-date order, so it is not proof.
    evidence["invoice_order_misleading"] = bool(dup["created_at"] < legit["created_at"])


def check_other_periods(row, invoices, flags, evidence):
    same_agreement = invoices[(invoices["agreement_id"] == row["agreement_id"])
                              & (invoices["invoice_id"] != row["invoice_id"])
                              & (invoices["period_start"] != row["period_start"])]
    if len(same_agreement) > 0:
        flags.append("same_agreement_other_period")
        evidence["other_period_invoice"] = same_agreement.iloc[0]["invoice_id"]


def history_check(invoice_id, data, tie_rng=None, config=None):
    if tie_rng is None:
        tie_rng = np.random.RandomState(TIE_SEED)
    if config is None:
        config = default_config()
    invoices = data["invoices"]
    row = invoices[invoices["invoice_id"] == invoice_id].iloc[0]

    flags = []
    evidence = {}
    check_past_billing(row, data["history"], flags, evidence, config)
    check_second_agreement(row, invoices, data["agreements"], flags, evidence, tie_rng)
    check_other_periods(row, invoices, flags, evidence)

    return {"stage": "history", "flags": flags, "evidence": evidence}
