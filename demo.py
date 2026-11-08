"""Run the whole pipeline on one disputed invoice.
Change INVOICE_ID below to look at another invoice.
"""
import json

from pipeline.data import load
from pipeline.run_pipeline import run_pipeline

INVOICE_ID = "INV-00001"

data = load("synthetic_data")

print(json.dumps(run_pipeline(INVOICE_ID, data), indent=2, default=str))
