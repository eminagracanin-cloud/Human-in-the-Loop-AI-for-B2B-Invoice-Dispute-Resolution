# NOTE: reordering random draws in this file changes the generated data.
"""Makes synthetic invoice-dispute data: CRM quotes, ERP billing agreements and
invoices, BI billing history, tickets and ground truth. All data is invented.
A billing agreement is any standing arrangement a customer is billed under.
 
Usage: python generate_cases.py
Makes all three data folders listed in DATASETS below: the messy data, the clean
data (messiness 0) and the drift data (price rise from DRIFT_DATE).
"""
import os
from datetime import date, timedelta
 
import numpy as np
import pandas as pd
 
# Three dispute types, and three possible true causes for each:
#   sync_error      CRM and ERP disagree, so the data proves it -> credit
#   human_error     a sales rep entered something odd; data cannot prove it
#                   -> ask the rep
#   customer_wrong  nothing is wrong -> no fault
DISPUTE_TYPES = ["wrong_price", "duplicate_charge", "wrong_quantity"]
 
# =============================================================================
# SETTINGS - every share and threshold that shapes the data is in this block.
# The numbers are placeholders: each company should replace them with its own
# numbers. Two come from my reading of the practitioner interviews
# (the new/existing order split and the no-history share); all others are
# invented. The matching thresholds for the pipeline are in pipeline/settings.py.
# =============================================================================
 
# Cause mix: what really caused each dispute
SHARE_SYNC = 0.40                   # CRM and ERP disagree (system error)
SHARE_HUMAN = 0.35                  # an account owner entered something odd; the rest is customer_wrong
HUMAN_MISTAKE_SHARE = 0.70          # of the human errors; the rest: account owner says "legitimate"
STALE_UPDATE_SHARE = 0.5            # of the sync errors: CRM edit never reached ERP (the rest: wrong value copied)
 
# Order types, for wrong_price and wrong_quantity cases only (duplicates are
# always "existing"). The 10/90 split is my estimate from the interviews.
#   new       first invoice on a one-off order, so it has no billing history
#   existing  a recurring agreement that keeps billing until it is cancelled
NEW_ORDER_SHARE = 0.10
 
# Billing history and tickets
HIST_MONTHS = 6                     # months of history for a long-standing customer
THIN_HISTORY_MONTHS = [1, 2]        # months of history for a new customer with a little
VAGUE_TICKET_SHARE = 0.30           # tickets that do not say what is wrong
DUP_REF_ORIGINAL_SHARE = 0.30       # duplicate tickets that cite the legit invoice
DUP_ORDER_MISLEAD_SHARE = 0.30      # duplicates where invoice order contradicts start dates
 
# Messy scenarios per (dispute type, cause): (tag, share of that group).
# Without them the generator and the pipeline share the same rules and the
# pipeline scores 100 percent. The no_history share is my interview
# estimate (about 1 percent of all cases); every other share is invented.
# The messiness scale (see DATASETS below) scales all of them, including no_history.
NO_HISTORY_SHARE = .01              # customer with zero billing history
THIN_HISTORY_SHARE = .005           # 1-2 months of history; kept below no_history
HISTORY_TAGS = [("no_history", NO_HISTORY_SHARE), ("thin_history", THIN_HISTORY_SHARE)]
SCENARIOS = {
    ("wrong_price", "sync_error"): [("short_lag", .15), ("near_jump", .10)] + HISTORY_TAGS,
    ("wrong_price", "human_error"): [("small_deviation", .15)] + HISTORY_TAGS,
    ("wrong_price", "customer_wrong"): [("legit_step", .20), ("change_after_invoice", .15),
                                        ("rounding_noise", .20)] + HISTORY_TAGS,
    ("wrong_quantity", "sync_error"): [("short_lag", .15)] + HISTORY_TAGS,
    ("wrong_quantity", "human_error"): HISTORY_TAGS,
    ("wrong_quantity", "customer_wrong"): [("legit_step", .25),
                                           ("change_after_invoice", .15)] + HISTORY_TAGS,
    ("duplicate_charge", "sync_error"): [("start_tie", .20)] + HISTORY_TAGS,
    ("duplicate_charge", "human_error"): [("start_tie", .15)] + HISTORY_TAGS,
    ("duplicate_charge", "customer_wrong"): [("legit_addon", .25)] + HISTORY_TAGS,
}
 
# How big the price and quantity errors are
PRICE_CUTS = [0.05, 0.10, 0.15]     # CRM price below the ERP price, as a share
DECIMAL_SHIFT_FACTOR = 10           # ERP price this many times the CRM price
NEAR_JUMP_MIN, NEAR_JUMP_MAX = 2.4, 3.6              # about 3x: at the stage-1 threshold
HUMAN_PRICE_RISE_MIN, HUMAN_PRICE_RISE_MAX = 0.08, 0.25
SMALL_DEVIATION_MIN, SMALL_DEVIATION_MAX = 0.003, 0.015   # straddles the 0.5% tolerance
ROUNDING_NOISE_MIN, ROUNDING_NOISE_MAX = 0.001, 0.009
LEGIT_PRICE_RISE_MIN, LEGIT_PRICE_RISE_MAX = 0.05, 0.20
LEGIT_CHANGE_MONTHS_MIN, LEGIT_CHANGE_MONTHS_MAX = 1, 4   # how long ago a real change was made
SHORT_LAG_HOURS_MIN, SHORT_LAG_HOURS_MAX = 1, 72          # CRM edited this long before billing
UNIT_STEPS = [5, 10, 15, 20, 25, 50]                      # units added or removed
ADD_ON_UNITS = range(5, 55, 5)                            # units on a legitimate add-on
 
# Tolerances for deciding that CRM and ERP agree
PRICE_MATCH_TOLERANCE = 0.005       # prices are equal within half a cent
QTY_MATCH_TOLERANCE = 0             # quantities must be equal
 
# Drift, only in the drift data folder (all invented): from the drift date a known
# invoicing rule changes, so existing agreements get an announced price rise
# in the CRM, the ERP and the invoices, while the billing history keeps the old prices.
DRIFT_DATE = date(2025, 7, 1)       # first invoice period that is affected
DRIFT_PRICE_RISE = 0.05             # 5 percent
 
# What to make when the file is run: the seed, cases per dispute type, and the
# data folders as (folder name, messiness scale, with drift?). Messiness 0 gives
# the clean data without the messy scenarios (new orders are still made).
SEED = 42
PER_TYPE = 100
DATASETS = [("synthetic_data", 1.0, False),
            ("synthetic_data_clean", 0.0, False),
            ("synthetic_data_drift", 1.0, True)]
 
# ============================ end of settings ================================
 
HISTORY_SCENARIOS = ["no_history", "thin_history", "legit_step",
                     "rounding_noise", "small_deviation"]
 
LIST_PRICES = [12.50, 48.00, 7.90, 120.00, 33.00, 19.90,
               250.00, 5.50, 64.00, 88.00, 15.00, 310.00]
 
PRODUCTS = []
for i in range(1, len(LIST_PRICES) + 1):
    PRODUCTS.append(f"P{i:02d}")
PRICE_OF = dict(zip(PRODUCTS, LIST_PRICES))
 
CUSTOMERS = []
for i in range(1, 41):
    CUSTOMERS.append(f"C{i:03d}")
 
REPS = []
for i in range(1, 13):
    REPS.append(f"R{i:02d}")
 
TEXT = {
    "wrong_price": [
        "Hi, the price on invoice {inv} is higher than what we agreed. Please check and correct.",
        "We were charged a price on {inv} that does not match what we were promised. Can you review it?",
        "Invoice {inv}: the price per unit looks wrong compared with what we usually pay.",
        "Our agreed rate does not seem to be reflected on {inv}. Please look into it.",
    ],
    "duplicate_charge": [
        "We appear to have been billed twice for the same thing, see {inv}. Please check.",
        "Invoice {inv} looks like a duplicate of an invoice we already received.",
        "Hello, we received {inv} but believe we already paid for this.",
        "Double charge? {inv} seems to be the same charge as an earlier invoice.",
    ],
    "wrong_quantity": [
        "The quantity billed on {inv} is higher than what we have.",
        "Invoice {inv} charges for more units than we signed up for.",
        "The number of units on {inv} does not match what we use. Can you check?",
        "We are being billed for more than we agreed on {inv}.",
    ],
    "vague": [
        "We believe invoice {inv} is incorrect. Please review and advise.",
        "There is a problem with {inv}. Can someone take a look?",
        "We would like to dispute invoice {inv}.",
        "Our accounts team flagged {inv} as wrong. Please check.",
    ],
}
 
 
def next_id(counters, prefix):
    counters[prefix] = counters.get(prefix, 0) + 1
    return f"{prefix}-{counters[prefix]:05d}"
 
 
def money(x):
    return round(x + 1e-9, 2)
 
 
def month_start(d):
    return d.replace(day=1)
 
 
def add_months(d, k):
    year = d.year + (d.month - 1 + k) // 12
    month = (d.month - 1 + k) % 12 + 1
    return date(year, month, 1)
 
 
def rand_dt(rng, d):
    hour = rng.randint(7, 19)
    minute = rng.randint(0, 60)
    return pd.to_datetime(f"{d.year}-{d.month:02d}-{d.day:02d} {hour:02d}:{minute:02d}")
 
 
def count_by(rows, key):
    counts = {}
    for row in rows:
        counts[row[key]] = counts.get(row[key], 0) + 1
    return counts
 
 
def index_by(rows, key):
    lookup = {}
    for row in rows:
        lookup[row[key]] = row
    return lookup
 
 
def make_anchor(case, period):
    """Agreement start date and the CRM quote date that goes with it."""
    r = case["anchor_rng"]
    if case["n_hist"] < HIST_MONTHS:
        start = add_months(period, -max(case["n_hist"], 1))
    else:
        start = add_months(period, -(HIST_MONTHS + r.randint(1, 19)))
    start = start.replace(day=r.randint(1, 29))
    days_before = r.randint(5, 46)
    return start, rand_dt(r, start - timedelta(days=days_before))
 
 
def add_quote(case, price, qty, created_at, modified_at=None):
    quote_id = next_id(case["ids"], "QTE")
    if modified_at is None:
        modified_at = created_at
    case["quotes"].append(dict(
        quote_id=quote_id, customer_id=case["customer"], product_id=case["product"],
        crm_price=price, crm_qty=qty, sales_rep_id=case["rep"],
        created_at=created_at, last_modified_at=modified_at))
    return quote_id
 
 
def add_invoice(case, quote_id, qty, price, period, created_at,
                start=None, agreement_id=None):
    """Bills on a new agreement, or on an existing one if agreement_id is given."""
    if agreement_id is None:
        agreement_id = next_id(case["ids"], "AGR")
        if start is None:
            start = case["agreement_start"]
        case["agreements"].append(dict(
            agreement_id=agreement_id, quote_id=quote_id,
            customer_id=case["customer"], product_id=case["product"],
            qty=qty, unit_price=price, start_date=start))
    case["last_agreement_id"] = agreement_id
    invoice_id = next_id(case["ids"], "INV")
    case["invoices"].append(dict(
        invoice_id=invoice_id, agreement_id=agreement_id,
        customer_id=case["customer"], product_id=case["product"],
        qty=qty, unit_price=price, amount=money(qty * price),
        period_start=period, created_at=created_at))
    return invoice_id
 
 
def add_history(case, price, qty, before, new_price=None, new_qty=None, new_months=0):
    """Past monthly billing, newest month first. The newest new_months months
    use the new price and quantity (a real change that was already paid)."""
    for k in range(1, case["n_hist"] + 1):
        hist_price, hist_qty = price, qty
        if k <= new_months:
            hist_price, hist_qty = new_price, new_qty
        case["history"].append(dict(
            customer_id=case["customer"], product_id=case["product"],
            period_start=add_months(before, -k), unit_price=hist_price,
            qty=hist_qty, amount=money(hist_price * hist_qty)))
 
 
def add_earlier_quote(case, price, qty, day):
    """A quote made 5-30 days before `day` (used for amendments and add-ons)."""
    mrng = case["mrng"]
    days_before = mrng.randint(5, 31)
    return add_quote(case, price, qty, rand_dt(mrng, day - timedelta(days=days_before)))
 
 
def late_crm_change(case):
    """When the CRM was edited after the invoice but before the ticket. The
    invoice was right when it was issued."""
    mrng = case["mrng"]
    gap = (case["ticket_date"] - case["created"].date()).days
    days_later = mrng.randint(1, gap)
    return rand_dt(mrng, case["created"].date() + timedelta(days=days_later))
 
 
def swap_last_two_invoice_times(case):
    first, second = case["invoices"][-2], case["invoices"][-1]
    first["created_at"], second["created_at"] = second["created_at"], first["created_at"]
 
 
def new_result(root_cause, disputed, credit=0.0, credit_invoice="",
               misleading=0, param=""):
    return dict(root_cause=root_cause, disputed=disputed, credit=credit,
                credit_invoice=credit_invoice, misleading=misleading, param=param)
 
 
def price_sync_error(case, scn):
    rng, mrng = case["rng"], case["mrng"]
    p0, q0 = case["p0"], case["q0"]
    param = ""
 
    if scn == "short_lag":
        stale_update = True
    elif scn == "near_jump":
        stale_update = False
    else:
        stale_update = rng.random() < STALE_UPDATE_SHARE
 
    if stale_update:
        root = "update_not_synced"
        crm_price = money(p0 * (1 - rng.choice(PRICE_CUTS)))
        erp_price = p0
        if scn == "short_lag":
            modified = case["created"] - timedelta(hours=mrng.randint(SHORT_LAG_HOURS_MIN, SHORT_LAG_HOURS_MAX + 1))
        else:
            modified = case["created"] - timedelta(days=rng.randint(10, 41))
    else:
        crm_price = p0
        modified = None
        if scn == "near_jump":
            factor = mrng.uniform(NEAR_JUMP_MIN, NEAR_JUMP_MAX)
            root = "unit_conversion_error"
            param = f"erp_x{factor:.2f}"
        else:
            factor = DECIMAL_SHIFT_FACTOR
            root = "decimal_shift"
        erp_price = money(p0 * factor)
 
    quote_id = add_quote(case, crm_price, q0, case["quote_created"], modified)
    disputed = add_invoice(case, quote_id, q0, erp_price, case["period"], case["created"])
    add_history(case, p0, q0, case["period"])
    credit = money((erp_price - crm_price) * q0)
    return new_result(root, disputed, credit, param=param)
 
 
def price_human_error(case, scn, resolution):
    rng, mrng = case["rng"], case["mrng"]
    p0, q0 = case["p0"], case["q0"]
    param = ""
 
    if scn == "small_deviation":
        cents = max(1, round(p0 * mrng.uniform(SMALL_DEVIATION_MIN, SMALL_DEVIATION_MAX) * 100))
        rep_price = money(p0 + cents / 100)
        param = f"dev{100 * (rep_price - p0) / p0:.2f}pct"
    else:
        rep_price = money(p0 * (1 + rng.uniform(HUMAN_PRICE_RISE_MIN, HUMAN_PRICE_RISE_MAX)))
 
    quote_created = case["created"] - timedelta(days=rng.randint(15, 61))
    quote_id = add_quote(case, rep_price, q0, quote_created)
    disputed = add_invoice(case, quote_id, q0, rep_price, case["period"], case["created"])
    add_history(case, p0, q0, case["period"])
    credit = 0.0
    if resolution == "mistake":
        credit = money((rep_price - p0) * q0)
    return new_result("rep_entered_different_price", disputed, credit, param=param)
 
 
def price_legit_step(case):
    mrng = case["mrng"]
    p0, q0, period = case["p0"], case["q0"], case["period"]
    months_ago = mrng.randint(LEGIT_CHANGE_MONTHS_MIN, LEGIT_CHANGE_MONTHS_MAX + 1)
    new_price = money(p0 * (1 + mrng.uniform(LEGIT_PRICE_RISE_MIN, LEGIT_PRICE_RISE_MAX)))
    add_quote(case, p0, q0, case["quote_created"])
    quote_id = add_earlier_quote(case, new_price, q0, add_months(period, -months_ago))
    disputed = add_invoice(case, quote_id, q0, new_price, period, case["created"])
    add_history(case, p0, q0, period, new_price, q0, months_ago)
    return new_result("legitimate_price_change", disputed,
                      param=f"changed_{months_ago}m_ago")
 
 
def price_change_after_invoice(case):
    mrng = case["mrng"]
    p0, q0 = case["p0"], case["q0"]
    crm_price = money(p0 * (1 - mrng.choice(PRICE_CUTS)))
    quote_id = add_quote(case, crm_price, q0, case["quote_created"], late_crm_change(case))
    disputed = add_invoice(case, quote_id, q0, p0, case["period"], case["created"])
    add_history(case, p0, q0, case["period"])
    return new_result("crm_change_after_invoice", disputed)
 
 
def price_rounding_noise(case):
    mrng = case["mrng"]
    p0, q0 = case["p0"], case["q0"]
    cents = max(1, round(p0 * mrng.uniform(ROUNDING_NOISE_MIN, ROUNDING_NOISE_MAX) * 100))
    new_price = money(p0 + mrng.choice([-1, 1]) * cents / 100)
    quote_id = add_quote(case, new_price, q0, case["quote_created"])
    disputed = add_invoice(case, quote_id, q0, new_price, case["period"], case["created"])
    add_history(case, p0, q0, case["period"])
    return new_result("rounding_difference", disputed,
                      param=f"dev{100 * (new_price - p0) / p0:.2f}pct")
 
 
def price_no_error(case):
    p0, q0 = case["p0"], case["q0"]
    quote_id = add_quote(case, p0, q0, case["quote_created"])
    disputed = add_invoice(case, quote_id, q0, p0, case["period"], case["created"])
    add_history(case, p0, q0, case["period"])
    return new_result("no_error_found", disputed)
 
 
def wrong_price_case(case, cause, scn, resolution):
    if cause == "sync_error":
        return price_sync_error(case, scn)
    if cause == "human_error":
        return price_human_error(case, scn, resolution)
    if scn == "legit_step":
        return price_legit_step(case)
    if scn == "change_after_invoice":
        return price_change_after_invoice(case)
    if scn == "rounding_noise":
        return price_rounding_noise(case)
    return price_no_error(case)
 
 
def quantity_sync_error(case, scn):
    rng, mrng = case["rng"], case["mrng"]
    p0, q0 = case["p0"], case["q0"]
    units = rng.choice(UNIT_STEPS)
 
    if scn == "short_lag":
        stale_update = True
    else:
        stale_update = rng.random() < STALE_UPDATE_SHARE
 
    if stale_update:
        root = "update_not_synced"
        crm_qty, erp_qty = q0 - units, q0
        if scn == "short_lag":
            modified = case["created"] - timedelta(hours=mrng.randint(SHORT_LAG_HOURS_MIN, SHORT_LAG_HOURS_MAX + 1))
        else:
            modified = case["created"] - timedelta(days=rng.randint(10, 41))
    else:
        root = "field_mismatch"
        crm_qty, erp_qty = q0, q0 + units
        modified = None
 
    quote_id = add_quote(case, p0, crm_qty, case["quote_created"], modified)
    disputed = add_invoice(case, quote_id, erp_qty, p0, case["period"], case["created"])
    add_history(case, p0, q0, case["period"])
    credit = money((erp_qty - crm_qty) * p0)
    return new_result(root, disputed, credit)
 
 
def quantity_human_error(case, resolution):
    rng = case["rng"]
    p0, q0 = case["p0"], case["q0"]
    extra = rng.choice(UNIT_STEPS)
    rep_qty = q0 + extra
    quote_created = case["created"] - timedelta(days=rng.randint(15, 61))
    quote_id = add_quote(case, p0, rep_qty, quote_created)
    disputed = add_invoice(case, quote_id, rep_qty, p0, case["period"], case["created"])
    add_history(case, p0, q0, case["period"])
    credit = 0.0
    if resolution == "mistake":
        credit = money(extra * p0)
    return new_result("rep_entered_different_quantity", disputed, credit)
 
 
def quantity_legit_step(case):
    mrng = case["mrng"]
    p0, q0, period = case["p0"], case["q0"], case["period"]
    months_ago = mrng.randint(LEGIT_CHANGE_MONTHS_MIN, LEGIT_CHANGE_MONTHS_MAX + 1)
    extra = mrng.choice(UNIT_STEPS)
    add_quote(case, p0, q0, case["quote_created"])
    quote_id = add_earlier_quote(case, p0, q0 + extra, add_months(period, -months_ago))
    disputed = add_invoice(case, quote_id, q0 + extra, p0, period, case["created"])
    add_history(case, p0, q0, period, p0, q0 + extra, months_ago)
    return new_result("legitimate_quantity_change", disputed,
                      param=f"changed_{months_ago}m_ago")
 
 
def quantity_change_after_invoice(case):
    mrng = case["mrng"]
    p0, q0 = case["p0"], case["q0"]
    crm_qty = q0 - mrng.choice(UNIT_STEPS)
    quote_id = add_quote(case, p0, crm_qty, case["quote_created"], late_crm_change(case))
    disputed = add_invoice(case, quote_id, q0, p0, case["period"], case["created"])
    add_history(case, p0, q0, case["period"])
    return new_result("crm_change_after_invoice", disputed)
 
 
def quantity_no_error(case):
    p0, q0 = case["p0"], case["q0"]
    quote_id = add_quote(case, p0, q0, case["quote_created"])
    disputed = add_invoice(case, quote_id, q0, p0, case["period"], case["created"])
    add_history(case, p0, q0, case["period"])
    return new_result("no_error_found", disputed)
 
 
def wrong_quantity_case(case, cause, scn, resolution):
    if cause == "sync_error":
        return quantity_sync_error(case, scn)
    if cause == "human_error":
        return quantity_human_error(case, resolution)
    if scn == "legit_step":
        return quantity_legit_step(case)
    if scn == "change_after_invoice":
        return quantity_change_after_invoice(case)
    return quantity_no_error(case)
 
 
def duplicate_legit_addon(case):
    mrng = case["mrng"]
    p0, q0, period, created = case["p0"], case["q0"], case["period"], case["created"]
    months_ago = mrng.randint(LEGIT_CHANGE_MONTHS_MIN, LEGIT_CHANGE_MONTHS_MAX + 1)
    extra = mrng.choice(ADD_ON_UNITS)
    add_on_start = add_months(period, -months_ago).replace(day=mrng.randint(1, 29))
 
    first_quote = add_quote(case, p0, q0, case["quote_created"])
    first = add_invoice(case, first_quote, q0, p0, period, created)
    second_quote = add_earlier_quote(case, p0, extra, add_on_start)
    second_created = created + timedelta(minutes=mrng.randint(1, 601))
    second = add_invoice(case, second_quote, extra, p0, period, second_created,
                         start=add_on_start)
    add_history(case, p0, q0, period, p0, q0 + extra, months_ago)
 
    disputed = second
    if mrng.random() < DUP_REF_ORIGINAL_SHARE:
        disputed = first
    return new_result("legitimate_second_agreement", disputed,
                      param=f"addon_{months_ago}m_ago")
 
 
def duplicate_consecutive_periods(case):
    rng, ticket_date = case["rng"], case["ticket_date"]
    p0, q0 = case["p0"], case["q0"]
    created = rand_dt(rng, ticket_date - timedelta(days=rng.randint(35, 46)))
    period = month_start(created.date())
    case["created"], case["period"] = created, period
    case["agreement_start"], case["quote_created"] = make_anchor(case, period)
 
    quote_id = add_quote(case, p0, q0, case["quote_created"])
    add_invoice(case, quote_id, q0, p0, period, created)
    next_created = created + timedelta(days=rng.randint(28, 32))
    second = add_invoice(case, None, q0, p0, add_months(period, 1), next_created,
                         agreement_id=case["last_agreement_id"])
    add_history(case, p0, q0, period)
    return new_result("consecutive_periods", second)
 
 
def duplicate_twin_agreements(case, cause, scn, resolution):
    """The same thing billed twice on two agreements, because of a sync
    error (double_sync) or because the rep made a second quote."""
    rng = case["rng"]
    p0, q0, period, created = case["p0"], case["q0"], case["period"], case["created"]
    tie = scn == "start_tie"
 
    if cause == "sync_error":
        root = "double_sync"
        quote_id = add_quote(case, p0, q0, case["quote_created"])
        first = add_invoice(case, quote_id, q0, p0, period, created)
        second_created = created + timedelta(minutes=rng.randint(5, 2881))
        second_start = second_created.date()
        if tie:
            second_start = case["agreement_start"]
        second = add_invoice(case, quote_id, q0, p0, period, second_created,
                             start=second_start)
        credit = money(p0 * q0)
    else:
        root = "second_quote_created"
        quote_1 = add_quote(case, p0, q0, case["quote_created"])
        first = add_invoice(case, quote_1, q0, p0, period, created)
        quote_2_created = created + timedelta(hours=rng.randint(1, 21))
        quote_2 = add_quote(case, p0, q0, quote_2_created)
        second_created = quote_2_created + timedelta(hours=rng.randint(1, 21))
        second_start = quote_2_created.date()
        if tie:
            second_start = case["agreement_start"]
        second = add_invoice(case, quote_2, q0, p0, period, second_created,
                             start=second_start)
        credit = 0.0
        if resolution == "mistake":
            credit = money(p0 * q0)
    add_history(case, p0, q0, period)
 
    misleading = 0
    if rng.random() < DUP_ORDER_MISLEAD_SHARE:
        swap_last_two_invoice_times(case)
        misleading = 1
 
    disputed = second
    if rng.random() < DUP_REF_ORIGINAL_SHARE:
        disputed = first
    credit_invoice = ""
    if credit > 0:
        credit_invoice = second
    return new_result(root, disputed, credit, credit_invoice, misleading)
 
 
def duplicate_charge_case(case, cause, scn, resolution):
    if scn == "start_tie":
        case["agreement_start"] = case["created"].date()
    if cause == "customer_wrong" and scn == "legit_addon":
        return duplicate_legit_addon(case)
    if cause == "customer_wrong":
        return duplicate_consecutive_periods(case)
    return duplicate_twin_agreements(case, cause, scn, resolution)
 
 
def start_case(rng, mrng, counters, customer, product, ticket_date, scn, order_type):
    """Draws the basics shared by all cases and returns them as a dict."""
    case = dict(rng=rng, mrng=mrng, ids=counters, customer=customer,
                product=product, ticket_date=ticket_date, order_type=order_type,
                quotes=[], agreements=[], invoices=[], history=[], last_agreement_id=None)
    case["p0"] = money(PRICE_OF[product] * rng.choice([0.80, 0.85, 0.90, 0.95, 1.00]))
    case["q0"] = rng.choice(range(60, 205, 5))
    case["rep"] = rng.choice(REPS)
 
    days_before = rng.randint(3, 21)
    case["created"] = rand_dt(rng, ticket_date - timedelta(days=days_before))
    case["period"] = month_start(case["created"].date())
 
    case["n_hist"] = HIST_MONTHS
    if scn == "no_history" or order_type == "new":
        case["n_hist"] = 0
    if scn == "thin_history":
        case["n_hist"] = mrng.choice(THIN_HISTORY_MONTHS)
    case["anchor_rng"] = rng
    if case["n_hist"] < HIST_MONTHS:
        case["anchor_rng"] = mrng
    case["agreement_start"], case["quote_created"] = make_anchor(case, case["period"])
    return case
 
 
def find_row(rows, key, value):
    for row in rows:
        if row[key] == value:
            return row
    return None
 
 
def crm_and_erp_disagree(case, invoice_id):
    """True if the invoice's price or quantity differs from its CRM quote."""
    invoice = find_row(case["invoices"], "invoice_id", invoice_id)
    agreement = find_row(case["agreements"], "agreement_id", invoice["agreement_id"])
    quote = find_row(case["quotes"], "quote_id", agreement["quote_id"])
    price_differs = abs(quote["crm_price"] - invoice["unit_price"]) > PRICE_MATCH_TOLERANCE
    qty_differs = abs(quote["crm_qty"] - invoice["qty"]) > QTY_MATCH_TOLERANCE
    return price_differs or qty_differs
 
 
def is_ambiguous(dtype, cause, scn, order_type, n_hist, disagree):
    """1 if the data alone cannot separate this case from another cause."""
    if order_type == "existing" and disagree:
        return 1
    if n_hist == 0 and not disagree and cause != "sync_error" and dtype != "duplicate_charge":
        return 1
    return 0
 
 
def drifted_credit(case, truth, factor):
    """The correct credit after the price rise, worked out from the changed rows
    so that it still matches what the pipeline can read from the tables."""
    credit = truth["correct_credit"]
    if credit == 0:
        return 0.0
    invoice = find_row(case["invoices"], "invoice_id", truth["credit_invoice_id"])
    if truth["dispute_type"] == "duplicate_charge":
        return invoice["amount"]
    if truth["cause_class"] == "human_error":
        return money(credit * factor)
    agreement = find_row(case["agreements"], "agreement_id", invoice["agreement_id"])
    quote = find_row(case["quotes"], "quote_id", agreement["quote_id"])
    return money(invoice["amount"] - quote["crm_price"] * quote["crm_qty"])
 
 
def apply_drift(case, truth):
    """From the drift date, existing agreements get an announced price rise.
    A case counts as drifted if its (first) invoice period is on or after it."""
    truth["drifted"] = 0
    if case["order_type"] != "existing" or case["period"] < DRIFT_DATE:
        return
    truth["drifted"] = 1
    factor = 1 + DRIFT_PRICE_RISE
    for quote in case["quotes"]:
        quote["crm_price"] = money(quote["crm_price"] * factor)
    for agreement in case["agreements"]:
        agreement["unit_price"] = money(agreement["unit_price"] * factor)
    for invoice in case["invoices"]:
        invoice["unit_price"] = money(invoice["unit_price"] * factor)
        invoice["amount"] = money(invoice["qty"] * invoice["unit_price"])
    truth["correct_credit"] = drifted_credit(case, truth, factor)
 
 
def make_case(rng, mrng, counters, dtype, cause, resolution, customer, product,
              ticket_date, scn, order_type):
    case = start_case(rng, mrng, counters, customer, product, ticket_date, scn,
                      order_type)
    if dtype == "wrong_price":
        result = wrong_price_case(case, cause, scn, resolution)
    elif dtype == "wrong_quantity":
        result = wrong_quantity_case(case, cause, scn, resolution)
    else:
        result = duplicate_charge_case(case, cause, scn, resolution)
 
    credit = result["credit"]
    credit_invoice = result["credit_invoice"]
    if dtype != "duplicate_charge" and credit > 0:
        credit_invoice = result["disputed"]
 
    vague = rng.random() < VAGUE_TICKET_SHARE
    if vague:
        template = rng.choice(TEXT["vague"])
    else:
        template = rng.choice(TEXT[dtype])
    ticket_id = next_id(counters, "TKT")
    ticket = dict(ticket_id=ticket_id, ticket_date=ticket_date, customer_id=customer,
                  text=template.format(inv=result["disputed"]))
 
    outcomes = {"sync_error": "credit_system_error",
                "human_error": "escalate_to_sales_rep",
                "customer_wrong": "no_fault"}
    rep_response = ""
    if cause == "human_error":
        rep_response = resolution
    final_resolution = "no_credit"
    if credit > 0:
        final_resolution = "credit"
 
    truth = dict(
        ticket_id=ticket_id, invoice_id=result["disputed"], dispute_type=dtype,
        cause_class=cause, root_cause=result["root_cause"],
        expected_pipeline_outcome=outcomes[cause], rep_response=rep_response,
        final_resolution=final_resolution, correct_credit=credit,
        credit_invoice_id=credit_invoice, vague_ticket=int(vague),
        invoice_order_misleading=result["misleading"])
 
    param = result["param"]
    if param == "" and scn == "thin_history":
        param = f"history_months={case['n_hist']}"
    disagree = False
    if dtype != "duplicate_charge":
        disagree = crm_and_erp_disagree(case, result["disputed"])
    truth["messiness"] = scn
    truth["messiness_param"] = param
    truth["ambiguous"] = is_ambiguous(dtype, cause, scn, order_type,
                                      case["n_hist"], disagree)
    truth["order_type"] = order_type
 
    return case, ticket, truth
 
 
def pick_scenario(mrng, dtype, cause, scale):
    """Picks a messy scenario for one case, or "" to keep it clean."""
    draw = mrng.random()
    cumulative = 0.0
    for tag, share in SCENARIOS[(dtype, cause)]:
        cumulative += share * scale
        if draw < cumulative:
            return tag
    return ""
 
 
def build_plan(rng, per_type):
    """One (dispute type, cause, rep answer) entry per case, shuffled."""
    n_sync = round(per_type * SHARE_SYNC)
    n_human = round(per_type * SHARE_HUMAN)
    n_mistake = int(n_human * HUMAN_MISTAKE_SHARE + 0.5)
    n_customer = per_type - n_sync - n_human
    plan = []
    for dtype in DISPUTE_TYPES:
        plan += [(dtype, "sync_error", "")] * n_sync
        plan += [(dtype, "human_error", "mistake")] * n_mistake
        plan += [(dtype, "human_error", "legitimate")] * (n_human - n_mistake)
        plan += [(dtype, "customer_wrong", "")] * n_customer
    rng.shuffle(plan)
    return plan
 
 
def build_order_types(plan, seed):
    """"new" or "existing" for each case. Uses its own random generator, so the
    clean and the messy data get the same order types."""
    order_rng = np.random.RandomState(seed + 2)
    order_types = []
    for dtype, cause, resolution in plan:
        if dtype == "duplicate_charge":
            order_types.append("existing")
        elif order_rng.random() < NEW_ORDER_SHARE:
            order_types.append("new")
        else:
            order_types.append("existing")
    return order_types
 
 
def build_pairs_and_dates(rng, n_cases):
    """A unique (customer, product) per case, and spread-out ticket dates."""
    pairs = []
    for customer in CUSTOMERS:
        for product in PRODUCTS:
            pairs.append((customer, product))
    rng.shuffle(pairs)
 
    first_day, last_day = date(2025, 1, 25), date(2025, 12, 10)
    span = (last_day - first_day).days
    dates = []
    for i in range(n_cases):
        offset = int(i * span / n_cases) + rng.randint(0, 3)
        dates.append(first_day + timedelta(days=offset))
    return pairs, dates
 
 
def write_csv(path, rows):
    pd.DataFrame(rows).to_csv(path, index=False)
 
 
def check_basic_rules(tables, invoices_by_id, agreements_by_id):
    quote_ids = index_by(tables["crm_quotes"], "quote_id")
    assert len(invoices_by_id) == len(tables["erp_invoices"])
    assert len(agreements_by_id) == len(tables["erp_agreements"])
    assert len(quote_ids) == len(tables["crm_quotes"])
    for inv in tables["erp_invoices"]:
        assert abs(inv["amount"] - inv["qty"] * inv["unit_price"]) < 0.01
        assert inv["agreement_id"] in agreements_by_id
 
    for ticket, truth in zip(tables["tickets"], tables["ground_truth"]):
        invoice = invoices_by_id[truth["invoice_id"]]
        assert ticket["ticket_date"] > invoice["created_at"].date()
        assert truth["correct_credit"] >= 0
        if truth["correct_credit"] > 0:
            credited = invoices_by_id[truth["credit_invoice_id"]]
            assert truth["correct_credit"] <= credited["amount"] + 0.01
        else:
            assert truth["credit_invoice_id"] == ""
        if truth["cause_class"] == "customer_wrong":
            assert truth["correct_credit"] == 0
        if truth["cause_class"] == "sync_error":
            assert truth["correct_credit"] > 0
 
 
def check_duplicate_rule(tables, invoices_by_id, agreements_by_id):
    """The credited invoice is on the agreement with the NEWEST start date
    (the oldest start date is the real agreement). In a start-date tie the rule
    cannot decide, but either invoice is a correct credit, so the credited
    invoice here is just one of the two."""
    for truth in tables["ground_truth"]:
        if truth["dispute_type"] != "duplicate_charge" or truth["credit_invoice_id"] == "":
            continue
        credited = invoices_by_id[truth["credit_invoice_id"]]
        agreement_ids = []
        starts = []
        for inv in tables["erp_invoices"]:
            same_thing = (inv["customer_id"] == credited["customer_id"]
                          and inv["product_id"] == credited["product_id"]
                          and inv["period_start"] == credited["period_start"])
            if same_thing:
                if inv["agreement_id"] not in agreement_ids:
                    agreement_ids.append(inv["agreement_id"])
                starts.append(agreements_by_id[inv["agreement_id"]]["start_date"])
        assert len(agreement_ids) == 2
 
        credited_start = agreements_by_id[credited["agreement_id"]]["start_date"]
        if truth.get("messiness") == "start_tie":
            assert min(starts) == max(starts)
        else:
            assert credited_start == max(starts)
            assert starts.count(max(starts)) == 1
 
 
def history_counts(tables):
    counts = {}
    for row in tables["bi_billing_history"]:
        key = (row["customer_id"], row["product_id"])
        counts[key] = counts.get(key, 0) + 1
    return counts
 
 
def check_messy_scenarios(tables, invoices_by_id, agreements_by_id):
    history_rows = history_counts(tables)
    quotes_by_id = index_by(tables["crm_quotes"], "quote_id")
 
    for truth in tables["ground_truth"]:
        invoice = invoices_by_id[truth["invoice_id"]]
        n_rows = history_rows.get((invoice["customer_id"], invoice["product_id"]), 0)
        tag = truth["messiness"]
        if tag == "no_history":
            assert n_rows == 0
        if tag == "thin_history":
            assert 0 < n_rows < HIST_MONTHS
        if tag == "change_after_invoice":
            quote_id = agreements_by_id[invoice["agreement_id"]]["quote_id"]
            assert quotes_by_id[quote_id]["last_modified_at"] > invoice["created_at"]
            assert truth["correct_credit"] == 0
        if tag in ("short_lag", "near_jump"):
            assert truth["cause_class"] == "sync_error"
            assert truth["correct_credit"] > 0
        if tag in ("legit_step", "rounding_noise", "legit_addon"):
            assert truth["cause_class"] == "customer_wrong"
 
 
def total(rows, key):
    result = 0
    for row in rows:
        result += row[key]
    return result
 
 
def print_counts(label, rows, key):
    print(label, count_by(rows, key))
 
 
def check_order_types(tables, invoices_by_id, agreements_by_id):
    history_rows = history_counts(tables)
    quotes_by_id = index_by(tables["crm_quotes"], "quote_id")
 
    for truth in tables["ground_truth"]:
        invoice = invoices_by_id[truth["invoice_id"]]
        assert truth["order_type"] in ("new", "existing")
        if truth["dispute_type"] == "duplicate_charge":
            assert truth["order_type"] == "existing"
            continue
        n_rows = history_rows.get((invoice["customer_id"], invoice["product_id"]), 0)
        if truth["order_type"] == "new":
            assert n_rows == 0
            assert truth["messiness"] not in HISTORY_SCENARIOS
 
        quote_id = agreements_by_id[invoice["agreement_id"]]["quote_id"]
        quote = quotes_by_id[quote_id]
        disagree = (abs(quote["crm_price"] - invoice["unit_price"]) > PRICE_MATCH_TOLERANCE
                    or abs(quote["crm_qty"] - invoice["qty"]) > QTY_MATCH_TOLERANCE)
        if truth["order_type"] == "existing" and disagree:
            assert truth["ambiguous"] == 1
        if truth["cause_class"] == "sync_error":
            assert disagree
 
 
def print_summary(ground_truth, seed, messiness):
    print(f"Cases: {len(ground_truth)}  (seed={seed})")
    print_counts("By type:", ground_truth, "dispute_type")
    print_counts("By cause class:", ground_truth, "cause_class")
    human_cases = []
    for truth in ground_truth:
        if truth["rep_response"] != "":
            human_cases.append(truth)
    print_counts("Rep response (human_error):", human_cases, "rep_response")
    print_counts("Expected pipeline outcome:", ground_truth, "expected_pipeline_outcome")
    print_counts("Root causes:", ground_truth, "root_cause")
    print_counts("Order types:", ground_truth, "order_type")
    print("Vague tickets:", total(ground_truth, "vague_ticket"))
    print("Duplicate cases where invoice order misleads:",
          total(ground_truth, "invoice_order_misleading"))
    if messiness > 0:
        tags = {}
        for truth in ground_truth:
            tag = truth["messiness"]
            if tag == "":
                tag = "clean"
            tags[tag] = tags.get(tag, 0) + 1
        print(f"Messiness (messiness={messiness:.2f}):", tags)
    print("Ambiguous cases:", total(ground_truth, "ambiguous"))
    print(f"Total credit owed: {total(ground_truth, 'correct_credit'):.2f}")
 
 
def make_dataset(seed, per_type, out_folder, messiness, drift):
    """Makes one data folder."""
    rng = np.random.RandomState(seed)
    mrng = np.random.RandomState(seed + 1)
    counters = {}
    os.makedirs(out_folder, exist_ok=True)
 
    plan = build_plan(rng, per_type)
    pairs, dates = build_pairs_and_dates(rng, len(plan))
    order_types = build_order_types(plan, seed)
 
    names = ["crm_quotes", "erp_agreements", "erp_invoices",
             "bi_billing_history", "tickets", "ground_truth"]
    tables = {}
    for name in names:
        tables[name] = []
 
    for i in range(len(plan)):
        dtype, cause, resolution = plan[i]
        customer, product = pairs[i]
        order_type = order_types[i]
        scn = pick_scenario(mrng, dtype, cause, messiness)
        if order_type == "new" and scn in HISTORY_SCENARIOS:
            scn = ""
        case, ticket, truth = make_case(rng, mrng, counters, dtype, cause,
                                        resolution, customer, product,
                                        dates[i], scn, order_type)
        if drift:
            apply_drift(case, truth)
        tables["crm_quotes"] += case["quotes"]
        tables["erp_agreements"] += case["agreements"]
        tables["erp_invoices"] += case["invoices"]
        tables["bi_billing_history"] += case["history"]
        tables["tickets"].append(ticket)
        tables["ground_truth"].append(truth)
 
    for name in names:
        write_csv(os.path.join(out_folder, f"{name}.csv"), tables[name])
 
    invoices_by_id = index_by(tables["erp_invoices"], "invoice_id")
    agreements_by_id = index_by(tables["erp_agreements"], "agreement_id")
    check_basic_rules(tables, invoices_by_id, agreements_by_id)
    check_duplicate_rule(tables, invoices_by_id, agreements_by_id)
    check_messy_scenarios(tables, invoices_by_id, agreements_by_id)
    check_order_types(tables, invoices_by_id, agreements_by_id)
 
    print_summary(tables["ground_truth"], seed, messiness)
    if drift:
        print(f"Drifted cases (price rise from {DRIFT_DATE}):",
              total(tables["ground_truth"], "drifted"))
    print("All sanity checks passed.")
 
 
def main():
    for out_folder, messiness, drift in DATASETS:
        print("=" * 70)
        print("Making", out_folder)
        make_dataset(SEED, PER_TYPE, out_folder, messiness, drift)
 
 
if __name__ == "__main__":
    main()
