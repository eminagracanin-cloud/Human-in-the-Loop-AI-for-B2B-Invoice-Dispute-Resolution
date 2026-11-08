# Human-in-the-loop AI for B2B dispute resolution

Code for the REPAI 2026 workshop paper. All data is synthetic.

## Setup
    pip install -r requirements.txt

## Run
    python generate_cases.py    # makes synthetic_data, synthetic_data_clean and synthetic_data_drift
    python demo.py              # runs the three stages on one invoice (set INVOICE_ID in the file)
    python evaluate.py          # baseline vs v2 on both folders, sensitivity table
    python bias_test.py         # automation-bias test (simulated reviewers)
    python drift_test.py        # drift test (needs synthetic_data_drift)

There are no command-line options. Each script has a short settings block near the top
(seed, folders, shares); change a number there and run the script again.

## Course tools only
The code uses only imports, functions and methods that appear in the course material
(see COURSE_REFERENCES.md for the course notebook behind each one, and for the short
list of exceptions that go a step beyond the notebooks). Random numbers come
from numpy's `RandomState` with fixed seeds: the data is the same on every run, but it is
not the same data as in earlier versions of this project, so earlier result tables do not
apply.

## Structure
    generate_cases.py               synthetic data generator (300 cases); settings block at the top
    synthetic_data/                 CRM, ERP, BI, ticketing tables + ground truth (messy)
    synthetic_data_clean/           same cases without the messy scenarios
    synthetic_data_drift/           same cases as synthetic_data, with a price rise from the drift date
    pipeline/settings.py            every pipeline threshold in one place (replace with your own)
    pipeline/data.py                loads the tables
    pipeline/stage1_first_glance.py invoice sanity checks
    pipeline/stage2_history.py      history check + oldest-start-date duplicate rule
    pipeline/stage3_root_cause.py   root cause: "baseline" rules or "v2" rules (RULES_VERSION)
    pipeline/run_pipeline.py        chains the three stages
    evaluate.py                     scores the pipeline; baseline vs v2, breakdowns, sensitivity
    bias_test.py                    automation-bias test
    drift_test.py                   drift test
    results/                        CSVs and charts from evaluate.py, bias_test.py, drift_test.py
    COURSE_REFERENCES.md            which course notebook each tool comes from
    results/                        all CSVs and the two charts (see "Results files")

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
Every share and threshold lives in one clearly labelled block, so each company can replace
them with numbers from its own cases. Nothing else needs to change.
- `generate_cases.py`, the block between "SETTINGS" and "end of settings" at the top: the
  cause mix, the new/existing order split, the history and ticket shares, every messiness
  share and size, the CRM-versus-ERP tolerances and the drift.
- `pipeline/settings.py`: the stage 1 price jump, the stage 2 price and quantity
  tolerances and history reference, the stage 3 tolerances and rule version, documented
  price uplifts, the tie seed, the credit tolerance used by `evaluate.py`, and the
  automation-bias test parameters.

The numbers shipped are placeholders. The table at the end says which ones the author
took from the interviews and which are invented.

## The data

### Order types (wrong_price and wrong_quantity only)
Ground truth has an `order_type` column. Duplicate cases are always "existing". The 10/90
split is the author's estimate from the interviews.
- **new**: the first invoice on a one-off order, so it has no billing history (zero
  history rows). About 10 percent of the price and quantity cases. A new order skips the
  scenarios that need history (no_history, thin_history, legit_step, rounding_noise,
  small_deviation).
- **existing**: a recurring agreement that keeps billing until it is cancelled. About 90
  percent. Its CRM quote is edited in place and re-synced, so the link from invoice to quote
  never changes.

Because of that in-place editing, for an existing order where CRM and ERP disagree the
data cannot say why: it could be a human error, an invalid cancellation, a transfer or
a system error. Those cases get `ambiguous`=1. `expected_pipeline_outcome` keeps the
true outcome (a sync error is still credit_system_error), so asking the rep counts as
a safe escalation, not as a wrong answer. For a new order a disagreement stays
provable, so it is not ambiguous. Order types are drawn with their own random
generator, so the clean and the messy folders get the same order types.

Zero-history cases come from two sources: new orders (about 10 percent of price and
quantity cases) and the no_history scenario (about 1 percent of all cases, for a new
customer). Both are kept, so the total zero-history share is higher than 1 percent.

### Messiness layer (not from the interviews)
Without it the generator and the pipeline share the same rules and any rule-following
pipeline scores 100 percent. The layer re-labels about a quarter of the cases (cause-class
mix unchanged) with situations the rules do not handle trivially. The messiness
scale in `DATASETS` (generate_cases.py) scales the scenario shares, and 0 switches the
scenarios off (the order types stay), which gives `synthetic_data_clean`.
Ground truth has four extra columns: `messiness`, `messiness_param`, `ambiguous`, `order_type`.

| tag | what it is | true outcome |
|---|---|---|
| no_history | new customer with zero billing history, about 1 percent of cases | unchanged; with zero history and CRM = ERP, `ambiguous`=1 (human error vs no fault looks identical) |
| thin_history | new customer with 1-2 months of history, 0.5 percent of cases | unchanged; not ambiguous |
| legit_step | price or units changed 1-4 months ago and was paid since; history shows the step, CRM = ERP | no_fault |
| legit_addon | add-on billing agreement for the same customer/product/period with a different quantity and its own quote | no_fault |
| change_after_invoice | CRM edited after the invoice was issued, so CRM != ERP today but the invoice was right | no_fault |
| short_lag | CRM edited hours before billing, ERP not yet updated | credit_system_error |
| near_jump | ERP price about 3x off (2.4-3.6x), at the stage-1 threshold | credit_system_error |
| rounding_noise | invoice price differs from history by cents (0.1-0.9 percent) | no_fault |
| small_deviation | rep price off by cents (0.3-1.5 percent), straddling the 0.5 percent tolerance | escalate |
| start_tie | two duplicate billing agreements with the same start date, so the oldest-date rule cannot pick one | same as the underlying duplicate; not ambiguous, either invoice is a correct credit (interviews) |

`expected_pipeline_outcome` stays the TRUE outcome. For `ambiguous` cases the safe answer
is escalate_to_sales_rep, and the evaluation reports those separately from outright wrong
decisions. `ambiguous`=1 has two reasons: an existing order where CRM and ERP disagree, and
zero history with CRM = ERP. A start-date tie is not one of them.

### Drift data
`python generate_cases.py` also makes `synthetic_data_drift` (the entry with drift switched on in `DATASETS`): the same cases as
`synthetic_data`, but from the drift date (`DRIFT_DATE`, 1 July) the prices of existing
agreements rise by 5 percent in the CRM quote, the ERP agreement and the invoices, as a
legitimate announced uplift. The billing history keeps the old prices. The correct credits
are recomputed from the changed rows. `synthetic_data` and `synthetic_data_clean` are not
changed by this option.

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
on the same data. `evaluate.py` runs both.

*Baseline* (the author's simple rules, in this order): (1) duplicate candidate: one CRM quote
behind both agreements = credit the duplicate invoice, two quotes = ask the rep on the
second quote; (2) same agreement billed in another period = no fault; (3) invoice amount
more than one cent above CRM price x CRM quantity = credit the gap; (4) CRM and ERP agree but
price or quantity differs from history = ask the rep on the quote; (5) otherwise no fault.
There is deliberately no no-history rule and no check of when the CRM was last edited.

*v2* (the practitioners' rules, from the interviews). It first follows the link from the
invoice to the agreement to the CRM quote, then:
1. Duplicates as in the baseline. On a start-date tie it adds the note "credit one, close
   that agreement, keep the other active" (either invoice is a correct credit).
2. Same agreement billed for another period: no fault.
3. New order (the first invoice on its agreement, found as "no billing history"): if CRM and
   ERP disagree it is a sync error and a credit is proposed; if they agree there is nothing to
   compare with, so it escalates with the note "no history: check the customer's other
   tickets and ask colleagues".
4. Existing order (recurring agreement): if CRM and ERP disagree it escalates with the note
   "existing order: could be human error, invalid cancellation, transfer or system error".
5. Existing order with CRM and ERP in agreement: a customer has one fixed price that does not
   change by itself, so any difference in price or quantity from the history is flagged and
   escalated to the rep. Otherwise no fault.

The data has no agreement-type column, so v2 treats "no billing history" as a new order.

## Evaluation (`evaluate.py`)
Every case is put in exactly one category: exact (outcome right, credit amount within one
cent, and for duplicates the right invoice credited; for a start-date tie either invoice of
the pair is accepted), safe escalation (an ambiguous case sent to the rep, scored
separately), false credit (credit proposed where none is owed, or where a human should
decide), over-escalation (rep asked where nothing was wrong), missed error (an error exists
but was not credited or escalated) or credit detail wrong (right outcome, wrong amount or
invoice). It reports baseline versus v2 on `synthetic_data` and `synthetic_data_clean`, with
breakdowns by messiness tag, order type, dispute type and cause class, and one sensitivity
table: history reference (median, most_recent) times price tolerance (0, 0.5 and 1 percent).

## Automation-bias test (`bias_test.py`)
**This tests the measurement method, not real human behaviour.** The reviewers are
simulated and ALL their parameters are invented (`BIAS_*` in `pipeline/settings.py`). The
script takes the v2 analyses of `synthetic_data`, corrupts a share of them (default 10
percent) in ways a reader could spot from the evidence (wrong credit amount, wrong invoice
credited, wrong escalation target, an outcome that contradicts the evidence), and checks
that the evidence does show the right answer. A careful reviewer catches a visible error with
a fixed probability. A skimming reviewer's chance falls with every analysis passed in a
row and resets when it catches an error. It reports the catch rate by corruption type and by
position in the queue over many shuffled queues, with a fixed seed.

## Drift test (`drift_test.py`)
Runs v2 on a no-drift control, on the drift data with the uplift not documented, and on the
drift data with the uplift documented in `DOCUMENTED_UPLIFTS`. Reports exact accuracy and
over-escalation rate (over-escalated cases divided by all cases) by invoice month, and before
and after the drift date.

## Results files (`results/`)
- `baseline_*_cases.csv`: the baseline per-case results saved before v2 was added (unchanged).
- `cases_<rules>_<data>.csv`: per-case results for each rule set and folder.
- `summary.csv`, `breakdown.csv`, `sensitivity.csv`: the evaluation tables.
- `bias_by_type.csv`, `bias_by_position.csv`, `bias_catch_by_position.png`.
- `drift_summary.csv`, `drift_monthly.csv`, `drift_monthly_accuracy.png`.

## Every rule and setting: from the interviews or invented
"From interviews" means the author took it from the 7 practitioner interviews (the two
numbers are the author's estimates, not measured rates). Everything else is invented by the
author and should be replaced with a company's own numbers.

| rule or setting | where | value | source |
|---|---|---|---|
| Three stages in order: first glance, history, root cause | pipeline | - | from interviews |
| Oldest start date is the real agreement (duplicates) | stage 2 | - | from interviews |
| Start-date tie: credit one, close that agreement, keep the other | stage 3 note, evaluate | - | from interviews |
| Human errors cannot be proven from data: escalate to the rep | stage 3 | - | from interviews |
| A customer has one fixed price that does not change by itself | v2 rule 5 | - | from interviews |
| v2 rules 1-5 (new vs existing order, notes) | stage 3 v2 | - | from interviews |
| "No billing history" stands for a new order | stage 3 v2 | - | invented (the data has no agreement type) |
| Baseline rules 1-2 (duplicates, other period) | stage 3 baseline | - | from interviews |
| Baseline rules 3-5 (overbilled credit, history deviation, nothing found) | stage 3 baseline | - | invented |
| Start-date ties broken by a seeded coin flip | stage 2 | seed 2026 | invented |
| `PRICE_JUMP` price far above usual | stage 1 | 3.0x | invented |
| `AMOUNT_TOLERANCE` amount = quantity x price | stage 1 | 0.01 | invented |
| `PRICE_TOLERANCE` price tolerance against history | stage 2 | 0.5 percent (tested at 0, 0.5, 1) | invented |
| `QTY_TOLERANCE` quantity tolerance against history | stage 2 | 0 | invented |
| `HISTORY_REFERENCE` | stage 2 | median (tested: median, most_recent) | invented |
| `DOCUMENTED_UPLIFTS` | stage 2 | empty | invented |
| `RULES_VERSION` | stage 3 | v2 | invented |
| `OVERBILLED_TOLERANCE` | stage 3 baseline | 0.01 | invented |
| `CRM_ERP_PRICE_TOLERANCE`, `CRM_ERP_QTY_TOLERANCE` | stage 3 | 0.005, 0 | invented |
| `CREDIT_TOLERANCE` | evaluate.py | 0.01 | invented |
| `BIAS_*` (seed, corruption share 10 percent, 200 queues, 10 bins, careful 0.90, skimming 0.90 x 0.97 per step with floor 0.20, visibility per corruption type) | bias_test.py | see settings | invented |
| `NEW_ORDER_SHARE` new vs existing order | generate_cases.py | 10 / 90 percent | from interviews (author's estimate) |
| `NO_HISTORY_SHARE` customers with zero billing history | generate_cases.py | 1 percent of all cases | from interviews (author's estimate) |
| Existing order with CRM != ERP is ambiguous | generate_cases.py | - | from interviews |
| `SHARE_SYNC`, `SHARE_HUMAN` cause mix | generate_cases.py | 40, 35 (rest 25) percent | invented |
| `HUMAN_MISTAKE_SHARE` | generate_cases.py | 70 percent | invented |
| `STALE_UPDATE_SHARE` | generate_cases.py | 50 percent | invented |
| `HIST_MONTHS`, `THIN_HISTORY_MONTHS` | generate_cases.py | 6; 1-2 | invented |
| `VAGUE_TICKET_SHARE`, `DUP_REF_ORIGINAL_SHARE`, `DUP_ORDER_MISLEAD_SHARE` | generate_cases.py | 30, 30, 30 percent | invented |
| `THIN_HISTORY_SHARE` | generate_cases.py | 0.5 percent | invented |
| `SCENARIOS` shares per group (short lag, near jump, small deviation, legit step, change after invoice, rounding noise, start tie, legit add-on) | generate_cases.py | 10-25 percent of their groups | invented |
| `PRICE_CUTS`, `DECIMAL_SHIFT_FACTOR` | generate_cases.py | 5/10/15 percent; 10x | invented |
| `NEAR_JUMP_*`, `HUMAN_PRICE_RISE_*`, `SMALL_DEVIATION_*`, `ROUNDING_NOISE_*` | generate_cases.py | 2.4-3.6x; 8-25; 0.3-1.5; 0.1-0.9 percent | invented |
| `LEGIT_PRICE_RISE_*`, `LEGIT_CHANGE_MONTHS_*`, `SHORT_LAG_HOURS_*` | generate_cases.py | 5-20 percent; 1-4 months; 1-72 hours | invented |
| `UNIT_STEPS`, `ADD_ON_UNITS` | generate_cases.py | 5-50 units | invented |
| `PRICE_MATCH_TOLERANCE`, `QTY_MATCH_TOLERANCE` | generate_cases.py | 0.005, 0 | invented |
| `DRIFT_DATE`, `DRIFT_PRICE_RISE` | generate_cases.py | 1 July 2025, 5 percent | invented |

Known limitations: the ground truth for a start_tie names the later sync / second quote as
the credited invoice, but `evaluate.py` accepts either invoice of the pair. The generator
does not enforce that a quote predates its agreement's start date.
