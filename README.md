# Human-in-the-loop AI for B2B dispute resolution

Code for the REPAI 2026 workshop paper. All data is synthetic.

## Setup

```
pip install -r requirements.txt
```

## Run

```
python generate_cases.py   # makes synthetic_data, synthetic_data_clean and synthetic_data_drift
python demo.py             # runs the three stages on one invoice (set INVOICE_ID in the file)
python evaluate.py         # baseline vs v2 on both folders, sensitivity table
python bias_test.py        # automation-bias test (simulated reviewers)
python drift_test.py       # drift test (needs synthetic_data_drift)
```

There are no command-line options. Each script has a short settings block near the top
(seed, folders, shares); change a number there and run the script again.

## Structure

```
generate_cases.py                synthetic data generator (300 cases); settings block at the top
synthetic_data/                  CRM, ERP, BI, ticketing tables + ground truth (messy)
synthetic_data_clean/            same cases without the messy scenarios
synthetic_data_drift/            same cases as synthetic_data, with a price rise from the drift date
pipeline/settings.py             every pipeline threshold in one place (replace with your own)
pipeline/data.py                 loads the tables
pipeline/stage1_first_glance.py  invoice sanity checks
pipeline/stage2_history.py       history check + oldest-start-date duplicate rule
pipeline/stage3_root_cause.py    root cause: "baseline" rules or "v2" rules (RULES_VERSION)
pipeline/run_pipeline.py         chains the three stages
evaluate.py                      scores the pipeline; baseline vs v2, breakdowns, sensitivity
bias_test.py                     automation-bias test
drift_test.py                    drift test
results/                         CSVs and charts from evaluate.py, bias_test.py, drift_test.py
```

## System names (generic)

CRM = sales system, ERP = billing system, BI layer = reporting, ticketing = support desk.

## Terms

A **billing agreement** is any standing arrangement a customer is billed under
(a service contract, a lease or a subscription). Its ids look like AGR-00001 and
they are stored in `erp_agreements.csv`. A **one-off order** is billed once; a
**recurring agreement** keeps billing until it is cancelled. Both are stored as billing
agreements. **Units** are the quantity billed on an agreement (licences, devices or
whatever the product is counted in).

## Settings: replace these numbers with your own

Every share and threshold is in one labelled block, so you can replace it with your own
numbers. Nothing else needs to change. Make your changes in these files:

- `generate_cases.py` (the SETTINGS block at the top)
- `pipeline/settings.py`: the stage 1 price jump, the stage 2 price and quantity
  tolerances and history reference, the stage 3 tolerances and rule version, documented
  price uplifts, the tie seed, the credit tolerance used by `evaluate.py`, and the
  automation-bias test parameters.

If you want different rules, edit pipeline/stage3_root_cause.py. 

Only two values come from the interviews: the split between new and existing orders
(about 10/90) and the share of cases without billing history (about 1 percent). Both are
my estimates, not measured rates. All other values are placeholders and should be replaced
with a company's own numbers.

## The pipeline

**Stage 1** checks the invoice itself (amount = quantity x price, positive values, price far
above the product's usual price). It only raises flags; it never changes the outcome.

**Stage 2** compares the invoice with the customer's billing history (the reference is the
`median` of the past months or the `most_recent` month, `HISTORY_REFERENCE`) and looks for
a second agreement billing the same thing. The price tolerance is `PRICE_TOLERANCE`. A list
of documented uplifts (`DOCUMENTED_UPLIFTS`, effective date and factor) multiplies the
history price, so an announced price rise is not flagged. Start-date ties are broken by a
seeded random choice (never by invoice id or row order) and recorded as `start_date_tie`.

**Stage 3** has two rule sets, chosen by `RULES_VERSION` ("baseline" or "v2") so both can run
on the same data. `evaluate.py` runs both. The v2 rules are listed in Table 1 of the paper.

The data has no agreement-type column, so v2 treats "no billing history" as a new order.

## Known limitations

The ground truth for a start_tie names the later sync / second quote as the credited
invoice, but `evaluate.py` accepts either invoice of the pair. The generator does not
enforce that a quote predates its agreement's start date.
