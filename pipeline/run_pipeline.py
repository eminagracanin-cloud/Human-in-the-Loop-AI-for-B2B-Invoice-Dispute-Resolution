# Chains the three stages for one disputed invoice, or for a list of them.
import numpy as np

from pipeline.settings import TIE_SEED, default_config
from pipeline.stage1_first_glance import first_glance
from pipeline.stage2_history import history_check
from pipeline.stage3_root_cause import root_cause


def run_pipeline(invoice_id, data, tie_rng=None, config=None):
    s1 = first_glance(invoice_id, data)
    s2 = history_check(invoice_id, data, tie_rng, config)
    s3 = root_cause(invoice_id, data, s1, s2, config)
    return {"invoice_id": invoice_id, "stage1": s1, "stage2": s2, "stage3": s3}


def run_all(invoice_ids, data, config=None):
    if config is None:
        config = default_config()
    tie_rng = np.random.RandomState(TIE_SEED)
    results = []
    for invoice_id in invoice_ids:
        results.append(run_pipeline(invoice_id, data, tie_rng, config))
    return results
