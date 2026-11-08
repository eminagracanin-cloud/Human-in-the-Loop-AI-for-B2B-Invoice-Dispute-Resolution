"""Load the source-system tables from the synthetic data folder."""
import pandas as pd


def load(folder="synthetic_data"):
    return {
        "quotes": pd.read_csv(f"{folder}/crm_quotes.csv",
                              parse_dates=["created_at", "last_modified_at"]),
        "agreements": pd.read_csv(f"{folder}/erp_agreements.csv",
                                  parse_dates=["start_date"]),
        "invoices": pd.read_csv(f"{folder}/erp_invoices.csv",
                                parse_dates=["period_start", "created_at"]),
        "history": pd.read_csv(f"{folder}/bi_billing_history.csv",
                               parse_dates=["period_start"]),
    }
