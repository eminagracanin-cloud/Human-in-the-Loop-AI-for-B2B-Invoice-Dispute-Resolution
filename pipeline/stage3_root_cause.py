"Stage 3 - Root cause. Proposes an outcome from the evidence of stages 1 and 2."

from pipeline.settings import (OVERBILLED_TOLERANCE, CRM_ERP_PRICE_TOLERANCE,
                               CRM_ERP_QTY_TOLERANCE, default_config)


TIE_NOTE = "credit one, close that agreement, keep the other active"

NO_HISTORY_NOTE = "no history: check the customer's other tickets and ask colleagues"
EXISTING_DISAGREE_NOTE = ("existing order: could be human error, invalid cancellation, "
                          "transfer or system error")


def quote_for_agreement(agreement_id, data):
    agreements = data["agreements"]
    agreement = agreements[agreements["agreement_id"] == agreement_id].iloc[0]
    quotes = data["quotes"]
    return quotes[quotes["quote_id"] == agreement["quote_id"]].iloc[0]


def make_result(outcome, rule, reason, evidence, credit_amount=0.0,
                credit_invoice="", escalate_to="", note=""):
    return {"stage": "root_cause", "outcome": outcome, "rule": rule,
            "reason": reason, "credit_amount": credit_amount,
            "credit_invoice": credit_invoice, "escalate_to": escalate_to,
            "note": note, "evidence": evidence}


def check_duplicate(s2, data, evidence):
    # Rule 1: two agreements bill the same thing.
    if "duplicate_candidate" not in s2["flags"]:
        return None
    found = s2["evidence"]
    legit_quote = quote_for_agreement(found["legit_agreement"], data)
    dup_quote = quote_for_agreement(found["duplicate_agreement"], data)
    evidence["rep_on_second_quote"] = dup_quote["sales_rep_id"]
    note = ""
    if found["start_date_tie"]:
        note = TIE_NOTE

    if legit_quote["quote_id"] == dup_quote["quote_id"]:
        return make_result(
            "credit_system_error", "1_duplicate_same_quote",
            "One CRM quote was synced into two agreements.", evidence,
            credit_amount=found["duplicate_amount"],
            credit_invoice=found["duplicate_invoice"], note=note)
    return make_result(
        "escalate_to_sales_rep", "1_duplicate_different_quotes",
        "Two different quotes created two agreements.", evidence,
        escalate_to=dup_quote["sales_rep_id"], note=note)


def check_renewal(s2, evidence):
    # Rule 2: the same agreement billed in another period is a normal renewal.
    if "same_agreement_other_period" not in s2["flags"]:
        return None
    return make_result("no_fault", "2_other_period",
                       "Two invoices for two different periods.", evidence)


def check_overbilled(invoice, quote, evidence):
    # Rule 3: the CRM is what was agreed, so billing more than CRM price times CRM quantity is a system error the data can prove.
    crm_amount = round(quote["crm_price"] * quote["crm_qty"], 2)
    gap = round(invoice["amount"] - crm_amount, 2)
    evidence["crm_amount"] = float(crm_amount)
    evidence["invoice_amount"] = float(invoice["amount"])
    evidence["overbilled_by"] = float(gap)
    if gap <= OVERBILLED_TOLERANCE:
        return None
    return make_result("credit_system_error", "3_overbilled_vs_crm",
                       "Invoice amount is higher than the CRM amount.", evidence,
                       credit_amount=float(gap), credit_invoice=invoice["invoice_id"])


def check_history_deviation(invoice, quote, s2, evidence):
    # Rule 4: CRM and ERP agree but both differ from past billing. Only the rep knows whether that was intended, so the rep is asked.
    same_price = abs(quote["crm_price"] - invoice["unit_price"]) < CRM_ERP_PRICE_TOLERANCE
    same_qty = abs(quote["crm_qty"] - invoice["qty"]) <= CRM_ERP_QTY_TOLERANCE
    if not (same_price and same_qty):
        return None
    differs = ("price_differs_from_history" in s2["flags"]
               or "qty_differs_from_history" in s2["flags"])
    if not differs:
        return None
    return make_result("escalate_to_sales_rep", "4_differs_from_history",
                       "CRM and ERP agree but differ from history.", evidence,
                       escalate_to=quote["sales_rep_id"])


def root_cause_baseline(invoice, quote, data, s1, s2):
    evidence = {"stage1_flags": list(s1["flags"])}      # for reading only

    result = check_duplicate(s2, data, evidence)
    if result is not None:
        return result
    result = check_renewal(s2, evidence)
    if result is not None:
        return result
    result = check_overbilled(invoice, quote, evidence)
    if result is not None:
        return result
    result = check_history_deviation(invoice, quote, s2, evidence)
    if result is not None:
        return result

    # Rule 5: nothing found.
    return make_result("no_fault", "5_nothing_found",
                       "No rule found a problem.", evidence)


#Version 2

def crm_and_erp_disagree(invoice, quote, evidence):
    crm_amount = round(quote["crm_price"] * quote["crm_qty"], 2)
    gap = round(invoice["amount"] - crm_amount, 2)
    evidence["crm_amount"] = float(crm_amount)
    evidence["invoice_amount"] = float(invoice["amount"])
    evidence["overbilled_by"] = float(gap)
    price_differs = abs(quote["crm_price"] - invoice["unit_price"]) >= CRM_ERP_PRICE_TOLERANCE
    qty_differs = abs(quote["crm_qty"] - invoice["qty"]) > CRM_ERP_QTY_TOLERANCE
    return price_differs or qty_differs, gap


def root_cause_v2(invoice, quote, data, s1, s2):
    evidence = {"stage1_flags": list(s1["flags"]), "quote_id": quote["quote_id"],
                "rep_on_quote": quote["sales_rep_id"]}

    result = check_duplicate(s2, data, evidence)
    if result is not None:
        return result
    result = check_renewal(s2, evidence)
    if result is not None:
        return result

    disagree, gap = crm_and_erp_disagree(invoice, quote, evidence)

    if "no_history" in s2["flags"]:
        evidence["order_type_found"] = "new"
        if disagree:
            credit = 0.0
            if gap > 0:
                credit = float(gap)
            return make_result("credit_system_error", "v2_new_order_disagree",
                               "New order: CRM and ERP disagree, so it is a sync error.",
                               evidence, credit_amount=credit,
                               credit_invoice=invoice["invoice_id"])
        return make_result("escalate_to_sales_rep", "v2_new_order_no_history",
                           "New order, CRM and ERP agree, and there is no history.",
                           evidence, escalate_to=quote["sales_rep_id"], note=NO_HISTORY_NOTE)

    evidence["order_type_found"] = "existing"
    if disagree:
        return make_result("escalate_to_sales_rep", "v2_existing_order_disagree",
                           "Existing order: CRM and ERP disagree.", evidence,
                           escalate_to=quote["sales_rep_id"], note=EXISTING_DISAGREE_NOTE)

    differs = ("price_differs_from_history" in s2["flags"]
               or "qty_differs_from_history" in s2["flags"])
    if differs:
        return make_result("escalate_to_sales_rep", "v2_existing_differs_from_history",
                           "Price or quantity differs from the customer's history.",
                           evidence, escalate_to=quote["sales_rep_id"])
    return make_result("no_fault", "v2_nothing_found",
                       "CRM, ERP and history agree.", evidence)


#Entry

def root_cause(invoice_id, data, s1, s2, config=None):
    if config is None:
        config = default_config()
    invoices = data["invoices"]
    invoice = invoices[invoices["invoice_id"] == invoice_id].iloc[0]
    quote = quote_for_agreement(invoice["agreement_id"], data)

    if config["rules_version"] == "baseline":
        return root_cause_baseline(invoice, quote, data, s1, s2)
    return root_cause_v2(invoice, quote, data, s1, s2)
