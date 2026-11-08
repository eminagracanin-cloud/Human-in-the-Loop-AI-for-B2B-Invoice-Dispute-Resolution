"""
Stage 1 - First glance.
Practitioners first open the invoice and check whether anything looks
suspicious. This stage only looks at the invoice itself (plus what a
normal price for that product looks like). It never decides anything;
it only raises flags that later stages can use.
"""

from pipeline.settings import PRICE_JUMP, AMOUNT_TOLERANCE


def first_glance(invoice_id, data):
    invoices = data["invoices"]
    row = invoices[invoices["invoice_id"] == invoice_id].iloc[0]

    flags = []
    evidence = {}

    # Check 1: does the arithmetic on the invoice add up?
    expected_amount = round(row["qty"] * row["unit_price"], 2)
    evidence["amount_on_invoice"] = float(row["amount"])
    evidence["qty_times_price"] = float(expected_amount)
    if abs(expected_amount - row["amount"]) > AMOUNT_TOLERANCE:
        flags.append("amount_mismatch")

    # Check 2: are quantity and price positive numbers?
    if row["qty"] <= 0 or row["unit_price"] <= 0:
        flags.append("non_positive_value")

    # Check 3: is the unit price far above what this product normally costs?
    same_product = invoices[invoices["product_id"] == row["product_id"]]
    usual_price = float(same_product["unit_price"].median())
    evidence["unit_price"] = float(row["unit_price"])
    evidence["usual_product_price"] = usual_price
    if row["unit_price"] > PRICE_JUMP * usual_price:
        flags.append("price_far_above_usual")

    return {"stage": "first_glance", "flags": flags, "evidence": evidence}
