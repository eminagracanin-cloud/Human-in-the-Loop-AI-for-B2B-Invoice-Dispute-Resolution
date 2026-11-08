# Settings for the pipeline: every threshold is in this file. The numbers are placeholders, so replace them with your own. None of them come from the interviews. 
# The matching settings for the data generator are at the top of generate_cases.py.
 
# Stage 1: first glance
PRICE_JUMP = 3.0                # flag a price above this many times the product's usual price
AMOUNT_TOLERANCE = 0.01         # invoice amount must equal quantity x price within one cent
 
# Stage 2: history check
PRICE_TOLERANCE = 0.005         # ignore price differences from history below 0.5 percent
QTY_TOLERANCE = 0               # quantity must equal the usual quantity
TIE_SEED = 2026                 # fixed seed for breaking start-date ties
 
# Stage 3: root cause
OVERBILLED_TOLERANCE = 0.01     # billed more than this above the CRM amount counts as a system error
CRM_ERP_PRICE_TOLERANCE = 0.005 # CRM and ERP prices are equal within half a cent
CRM_ERP_QTY_TOLERANCE = 0       # CRM and ERP quantities must be equal
 
# Evaluation (evaluate.py)
CREDIT_TOLERANCE = 0.01         # a credit is right if within one cent of the correct amount
 
# Rules and history reference
RULES_VERSION = "v2"            # "baseline" or "v2"
HISTORY_REFERENCE = "median"    # compare with the "median" of past months or the "most_recent" month
DOCUMENTED_UPLIFTS = []         # known price rises as (effective date "YYYY-MM-DD", factor), e.g. [("2025-07-01", 1.05)]
 
# Automation-bias test (bias_test.py). All values are invented, not measured.
BIAS_SEED = 2026
BIAS_CORRUPTION_SHARE = 0.10    # share of v2 analyses that are corrupted
BIAS_QUEUE_REPEATS = 200        # number of shuffled queues
BIAS_POSITION_BINS = 10         # queue positions are grouped into this many bins
BIAS_CAREFUL_CATCH = 0.90       # careful reviewer: chance of catching a visible error
BIAS_SKIM_START_CATCH = 0.90    # skimming reviewer: chance at the start of the queue
BIAS_SKIM_DECAY = 0.97          # multiplied after every analysis passed without a catch
BIAS_SKIM_FLOOR = 0.20          # lowest chance
# How visible each error type is (multiplies the catch chance)
BIAS_VISIBILITY = {"wrong_amount": 0.80, "wrong_invoice": 0.70,
                   "wrong_target": 0.60, "contradicts_evidence": 1.00}
 
 
def default_config():
    return {"rules_version": RULES_VERSION,
            "history_reference": HISTORY_REFERENCE,
            "price_tolerance": PRICE_TOLERANCE,
            "documented_uplifts": list(DOCUMENTED_UPLIFTS)}
