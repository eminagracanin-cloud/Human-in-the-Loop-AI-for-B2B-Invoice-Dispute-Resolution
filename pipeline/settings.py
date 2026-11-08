"""SETTINGS for the pipeline: every threshold is in this one file.

The numbers are placeholders. Each company should replace them with its own
numbers. The choices below are the author's and are not from the practitioner
interviews. The matching settings for the data generator are at the top of
generate_cases.py.
"""

# --- Stage 1: first glance
PRICE_JUMP = 3.0               # a price above this many times the product's usual price looks suspicious
AMOUNT_TOLERANCE = 0.01        # invoice amount must equal quantity x price within this (one cent)

# --- Stage 2: history check
PRICE_TOLERANCE = 0.005        # ignore price differences from history under this share (0.5 percent)
QTY_TOLERANCE = 0              # quantity must equal the usual quantity
TIE_SEED = 2026                # fixed, so a start-date tie is broken the same way on every run

# --- Stage 3: root cause
OVERBILLED_TOLERANCE = 0.01    # billed more than this above the CRM amount = system error (one cent)
CRM_ERP_PRICE_TOLERANCE = 0.005   # CRM and ERP unit prices count as equal within half a cent
CRM_ERP_QTY_TOLERANCE = 0         # CRM and ERP quantities must be equal

# --- Evaluation (evaluate.py)
CREDIT_TOLERANCE = 0.01        # a proposed credit is right if within this of the correct credit

# --- Stage 3 rules and the history reference
RULES_VERSION = "v2"           # "baseline" (the simple rules) or "v2" (the practitioners' rules, from interviews)
HISTORY_REFERENCE = "median"   # what an invoice is compared with: "median" of the past months or the "most_recent" month
# Documented price uplifts the pipeline should accept: (effective date "YYYY-MM-DD", price factor).
# Example: [("2025-07-01", 1.05)]. Empty means no uplift is documented, so any price change is flagged.
DOCUMENTED_UPLIFTS = []

# --- Automation-bias test (bias_test.py). ALL of these are INVENTED, not measured.
BIAS_SEED = 2026                    # fixed, so the test can be repeated exactly
BIAS_CORRUPTION_SHARE = 0.10        # share of the v2 analyses that are corrupted
BIAS_QUEUE_REPEATS = 200            # how many shuffled queues are simulated
BIAS_POSITION_BINS = 10             # queue positions are grouped into this many bins
BIAS_CAREFUL_CATCH = 0.90           # careful reviewer: fixed chance of catching a visible error
BIAS_SKIM_START_CATCH = 0.90        # skimming reviewer: chance at the start of the queue
BIAS_SKIM_DECAY = 0.97              # ... multiplied by this for every analysis passed in a row
BIAS_SKIM_FLOOR = 0.20              # ... but never lower than this
# How easy each corruption is to see from the evidence (multiplies the catch chance).
BIAS_VISIBILITY = {"wrong_amount": 0.80, "wrong_invoice": 0.70,
                   "wrong_target": 0.60, "contradicts_evidence": 1.00}


def default_config():
    """The settings that the stages read, as a dict, so a test can change one
    of them without editing this file."""
    return {"rules_version": RULES_VERSION,
            "history_reference": HISTORY_REFERENCE,
            "price_tolerance": PRICE_TOLERANCE,
            "documented_uplifts": list(DOCUMENTED_UPLIFTS)}
