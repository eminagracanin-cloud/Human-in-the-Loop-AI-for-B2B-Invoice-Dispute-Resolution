# Automation-bias test. It tests the measurement method, not real human behaviour: the reviewers are simulated with invented parameters (BIAS_* in pipeline/settings.py).
# Corrupts a share of the v2 analyses and lets a careful and a skimming reviewer check the queue. Reports the catch rate by corruption type and by position in the queue.
# Usage: python bias_test.py

import os

import os
 
import numpy as np
import matplotlib.pyplot as plt
 
from evaluate import load_truths, make_config, save_rows
from pipeline.data import load
from pipeline.run_pipeline import run_all
from pipeline.settings import (BIAS_SEED, BIAS_CORRUPTION_SHARE, BIAS_QUEUE_REPEATS,
                               BIAS_POSITION_BINS, BIAS_CAREFUL_CATCH,
                               BIAS_SKIM_START_CATCH, BIAS_SKIM_DECAY,
                               BIAS_SKIM_FLOOR, BIAS_VISIBILITY)
 
DATA_FOLDER = "synthetic_data"
CORRUPTION_SHARE = BIAS_CORRUPTION_SHARE
RESULTS_FOLDER = "results"
 
KINDS = ["wrong_amount", "wrong_invoice", "wrong_target", "contradicts_evidence"]
REVIEWERS = ["careful", "skimming"]
 
FLIPPED_OUTCOME = {"credit_system_error": "no_fault",
                   "escalate_to_sales_rep": "credit_system_error",
                   "no_fault": "credit_system_error"}
 
 
def kinds_for(stage3):
    """The corruptions that make sense for this analysis."""
    kinds = []
    if stage3["outcome"] == "credit_system_error":
        if stage3["credit_amount"] > 0:
            kinds.append("wrong_amount")
        kinds.append("wrong_invoice")
    if stage3["outcome"] == "escalate_to_sales_rep":
        kinds.append("wrong_target")
    kinds.append("contradicts_evidence")
    return kinds
 
 
def evidence_shows_truth(result, kind):
    """True if the right value can be read from the evidence."""
    stage3 = result["stage3"]
    found3 = stage3["evidence"]
    found2 = result["stage2"]["evidence"]
    if kind == "wrong_amount":
        if "overbilled_by" in found3 and abs(found3["overbilled_by"] - stage3["credit_amount"]) < 0.005:
            return True
        if "duplicate_amount" in found2 and abs(found2["duplicate_amount"] - stage3["credit_amount"]) < 0.005:
            return True
        return False
    if kind == "wrong_invoice":
        if stage3["credit_invoice"] == result["invoice_id"]:
            return True
        return stage3["credit_invoice"] == found2.get("duplicate_invoice")
    if kind == "wrong_target":
        rep_here = found3.get("rep_on_quote")
        rep_second = found3.get("rep_on_second_quote")
        return stage3["escalate_to"] == rep_here or stage3["escalate_to"] == rep_second
    return True
 
 
def corrupt(stage3, kind, invoice_ids, reps, rng):
    """A corrupted copy. The evidence is left as it was."""
    bad = dict(stage3)
    if kind == "wrong_amount":
        bad["credit_amount"] = round(stage3["credit_amount"] * 1.5, 2)
    elif kind == "wrong_invoice":
        other = stage3["credit_invoice"]
        while other == stage3["credit_invoice"]:
            other = rng.choice(invoice_ids)
        bad["credit_invoice"] = other
    elif kind == "wrong_target":
        other = stage3["escalate_to"]
        while other == stage3["escalate_to"]:
            other = rng.choice(reps)
        bad["escalate_to"] = other
    else:
        bad["outcome"] = FLIPPED_OUTCOME[stage3["outcome"]]
        if bad["outcome"] == "no_fault":
            bad["credit_amount"] = 0.0
            bad["credit_invoice"] = ""
        else:
            bad["credit_amount"] = 1000.0
    return bad
 
 
def catch_chance(reviewer, streak, kind):
    if reviewer == "careful":
        base = BIAS_CAREFUL_CATCH
    else:
        base = BIAS_SKIM_START_CATCH * (BIAS_SKIM_DECAY ** streak)
        if base < BIAS_SKIM_FLOOR:
            base = BIAS_SKIM_FLOOR
    return base * BIAS_VISIBILITY[kind]
 
 
def review_queue(kinds_in_queue, reviewer, rng):
    """One reviewer works through a queue. Returns (position, kind, caught) for each corrupted analysis."""
    streak = 0
    events = []
    for position in range(len(kinds_in_queue)):
        kind = kinds_in_queue[position]
        if kind is None:
            streak += 1
            continue
        caught = rng.random() < catch_chance(reviewer, streak, kind)
        events.append((position, kind, caught))
        if caught:
            streak = 0
        else:
            streak += 1
    return events
 
 
def add_event(table, key, caught):
    if key not in table:
        table[key] = [0, 0]
    table[key][0] += 1
    if caught:
        table[key][1] += 1
 
 
def rate(pair):
    if pair[0] == 0:
        return 0.0
    return 100.0 * pair[1] / pair[0]
 
 
def main():
    os.makedirs(RESULTS_FOLDER, exist_ok=True)
 
    data = load(DATA_FOLDER)
    truths = load_truths(DATA_FOLDER)
    invoice_ids = []
    for truth in truths:
        invoice_ids.append(truth["invoice_id"])
    results = run_all(invoice_ids, data, make_config("v2"))
 
    reps = sorted(set(data["quotes"]["sales_rep_id"]))
    n = len(results)
    n_bad = round(n * CORRUPTION_SHARE)
    rng = np.random.RandomState(BIAS_SEED)
 
    by_type = {}
    by_bin = {}
    overall = {}
    for reviewer in REVIEWERS:
        by_type[reviewer] = {}
        by_bin[reviewer] = {}
        overall[reviewer] = [0, 0]
    corrupted_counts = {}
    changed_copies = 0
    not_spottable = 0
 
    for repeat in range(BIAS_QUEUE_REPEATS):
        order = list(range(n))
        rng.shuffle(order)
        bad_positions = rng.choice(n, n_bad, replace=False)
        kinds_in_queue = [None] * n
        for position in bad_positions:
            result = results[order[position]]
            kind = rng.choice(kinds_for(result["stage3"]))
            kinds_in_queue[position] = kind
            corrupted_counts[kind] = corrupted_counts.get(kind, 0) + 1
            bad = corrupt(result["stage3"], kind, invoice_ids, reps, rng)
            if bad != result["stage3"]:
                changed_copies += 1
            if not evidence_shows_truth(result, kind):
                not_spottable += 1
 
        for reviewer in REVIEWERS:
            for position, kind, caught in review_queue(kinds_in_queue, reviewer, rng):
                add_event(by_type[reviewer], kind, caught)
                add_event(by_bin[reviewer], position * BIAS_POSITION_BINS // n, caught)
                overall[reviewer][0] += 1
                if caught:
                    overall[reviewer][1] += 1
 
    print("AUTOMATION-BIAS TEST on the v2 analyses of", DATA_FOLDER)
    print("This tests the measurement method, not real human behaviour.")
    print(f"{n} analyses, {n_bad} corrupted per queue ({CORRUPTION_SHARE * 100:.0f}%), "
          f"{BIAS_QUEUE_REPEATS} shuffled queues, seed {BIAS_SEED}.")
    total_corrupted = 0
    for kind in corrupted_counts:
        total_corrupted += corrupted_counts[kind]
    print(f"Corruptions made: {total_corrupted}; differing from the original: {changed_copies}; "
          f"not visible from the evidence: {not_spottable}")
    print("INVENTED reviewer parameters:")
    print(f"  careful: catches a visible error with probability {BIAS_CAREFUL_CATCH}")
    print(f"  skimming: starts at {BIAS_SKIM_START_CATCH}, times {BIAS_SKIM_DECAY} for every analysis "
          f"passed in a row, floor {BIAS_SKIM_FLOOR}")
    print(f"  visibility of each corruption (multiplies the chance): {BIAS_VISIBILITY}")
 
    print()
    print("Catch rate by corruption type")
    print(f"  {'corruption':24s}{'corrupted':>10s}{'careful':>10s}{'skimming':>10s}")
    type_csv = []
    for kind in KINDS:
        if kind not in corrupted_counts:
            continue
        careful = rate(by_type["careful"][kind])
        skimming = rate(by_type["skimming"][kind])
        print(f"  {kind:24s}{corrupted_counts[kind]:10d}{careful:9.1f}%{skimming:9.1f}%")
        type_csv.append({"corruption": kind, "corrupted": corrupted_counts[kind],
                         "careful_catch_pct": round(careful, 1),
                         "skimming_catch_pct": round(skimming, 1)})
    print(f"  {'ALL':24s}{overall['careful'][0]:10d}{rate(overall['careful']):9.1f}%"
          f"{rate(overall['skimming']):9.1f}%")
    type_csv.append({"corruption": "ALL", "corrupted": overall["careful"][0],
                     "careful_catch_pct": round(rate(overall["careful"]), 1),
                     "skimming_catch_pct": round(rate(overall["skimming"]), 1)})
 
    print()
    print("Catch rate by position in the queue")
    print(f"  {'positions':14s}{'corrupted':>10s}{'careful':>10s}{'skimming':>10s}")
    bin_csv = []
    middles = []
    careful_rates = []
    skimming_rates = []
    for b in range(BIAS_POSITION_BINS):
        first = b * n // BIAS_POSITION_BINS + 1
        last = (b + 1) * n // BIAS_POSITION_BINS
        careful = rate(by_bin["careful"][b])
        skimming = rate(by_bin["skimming"][b])
        label = f"{first}-{last}"
        print(f"  {label:14s}{by_bin['careful'][b][0]:10d}{careful:9.1f}%{skimming:9.1f}%")
        bin_csv.append({"positions": label, "corrupted": by_bin["careful"][b][0],
                        "careful_catch_pct": round(careful, 1),
                        "skimming_catch_pct": round(skimming, 1)})
        middles.append((first + last) / 2)
        careful_rates.append(careful)
        skimming_rates.append(skimming)
 
    save_rows(type_csv, os.path.join(RESULTS_FOLDER, "bias_by_type.csv"))
    save_rows(bin_csv, os.path.join(RESULTS_FOLDER, "bias_by_position.csv"))
 
    figure, axis = plt.subplots(figsize=(8, 4.5))
    axis.plot(middles, careful_rates, marker="o", color="#1f77b4", label="careful reviewer")
    axis.plot(middles, skimming_rates, marker="o", color="#c0392b", label="skimming reviewer")
    axis.set_ylim(0, 100)
    axis.set_xlabel("position in the queue")
    axis.set_ylabel("share of corruptions caught (%)")
    axis.set_title("Simulated reviewers, invented parameters: tests the method only")
    axis.legend(loc="lower left")
    figure.tight_layout()
    chart_path = os.path.join(RESULTS_FOLDER, "bias_catch_by_position.png")
    figure.savefig(chart_path, dpi=150)
    print()
    print(f"Saved {chart_path}, bias_by_type.csv, bias_by_position.csv in {RESULTS_FOLDER}/")
 
 
if __name__ == "__main__":
    main()
