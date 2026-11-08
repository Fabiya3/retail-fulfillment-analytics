import os
import sys
from pathlib import Path
import pandas as pd
import numpy as np

# Resolve base project directory dynamically (works whether run from root or /scripts)
BASE_DIR = Path(__file__).resolve().parent.parent

RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"

RAW_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# Case-insensitive search for your Excel file in data/raw
excel_candidates = list(RAW_DIR.glob("*.xlsx")) + list(RAW_DIR.glob("*.xls"))

if not excel_candidates:
    print(f"\n[ERROR] No Excel file found in: {RAW_DIR}")
    print("Please ensure your downloaded file (e.g. 'Online Retail.xlsx') is inside data/raw/\n")
    sys.exit(1)

raw_path = excel_candidates[0]
print(f"Loading raw transactional Excel workbook: {raw_path.name}")

# Use pd.read_excel with openpyxl engine
# (If you haven't yet, run: pip install openpyxl)
try:
    df_raw = pd.read_excel(raw_path, sheet_name=0, dtype={"CustomerID": str}, engine="openpyxl")
except ImportError:
    print("\n[ERROR] Missing 'openpyxl' library to read .xlsx files.")
    print("Run: pip install openpyxl\n")
    sys.exit(1)

print(f"Raw records loaded: {len(df_raw):,}")

# -------------------------------------------------------------------------
# 1. Data Cleaning & Hygiene
# -------------------------------------------------------------------------
df = df_raw.copy()

# Standardize column names (strip whitespace and lowercase)
df.columns = [col.strip().lower() for col in df.columns]

# Filter out missing CustomerID (guest checkouts)
df = df[df["customerid"].notna()].copy()
df["customer_id"] = "CUST_" + df["customerid"].astype(str).str.split(".").str[0]

# Standardize timestamps
df["order_timestamp"] = pd.to_datetime(df["invoicedate"])
df["order_date"] = df["order_timestamp"].dt.date

# Clean product descriptions
df["description"] = df["description"].fillna("UNKNOWN ITEM").astype(str).str.strip().str.upper()

# Handle Cancellations: 'C' prefix indicates returns/cancellations
df["is_cancelled"] = df["invoiceno"].astype(str).str.startswith("C")

# Filter out non-merchandise fees/postage line codes
clean_product_mask = ~df["stockcode"].astype(str).isin(["POST", "D", "M", "PADS", "DOT", "CRUK", "BANK CHARGES"])
df = df[clean_product_mask].copy()

# Filter out zero or negative pricing artifacts
df = df[df["unitprice"] > 0].copy()

# -------------------------------------------------------------------------
# 2. Financial Metrics & Outlier Flagging
# -------------------------------------------------------------------------
df["quantity_ordered"] = df["quantity"].abs()
df["line_total_revenue"] = df["quantity"] * df["unitprice"]

# Statistical IQR screening on positive transactions to flag bulk wholesale orders
valid_orders = df.loc[~df["is_cancelled"], "line_total_revenue"]
q1 = valid_orders.quantile(0.25)
q3 = valid_orders.quantile(0.75)
iqr = q3 - q1
upper_bound = q3 + (3.0 * iqr)

df["is_bulk_outlier"] = df["line_total_revenue"] > upper_bound

# -------------------------------------------------------------------------
# 3. Dimensional Decomposition (Star Schema)
# -------------------------------------------------------------------------

# Dimension: dim_customers
dim_customers = df.groupby("customer_id").agg(
    signup_date=("order_date", "min"),
    country=("country", "first")
).reset_index()

# Dimension: dim_products
dim_products = df.groupby("stockcode").agg(
    product_name=("description", "last"),
    typical_unit_price=("unitprice", "median")
).reset_index().rename(columns={"stockcode": "product_sku"})

# Fact: fact_order_lines
df["order_line_id"] = [f"LN_{i:08d}" for i in range(1, len(df) + 1)]

fact_order_lines = df[[
    "order_line_id",
    "invoiceno",
    "customer_id",
    "stockcode",
    "order_timestamp",
    "order_date",
    "quantity",
    "unitprice",
    "line_total_revenue",
    "is_cancelled",
    "is_bulk_outlier"
]].rename(columns={
    "invoiceno": "invoice_no",
    "stockcode": "product_sku",
    "unitprice": "unit_price"
})

# Dimension: dim_dates (Contiguous day calendar)
min_date = df["order_date"].min()
max_date = df["order_date"].max()
all_dates = pd.date_range(start=min_date, end=max_date, freq="D")

dim_dates = pd.DataFrame({
    "date_key": all_dates.strftime("%Y-%m-%d"),
    "full_date": all_dates,
    "year": all_dates.year,
    "quarter": "Q" + all_dates.quarter.astype(str),
    "month_number": all_dates.month,
    "month_name": all_dates.strftime("%B"),
    "day_name": all_dates.strftime("%A"),
    "is_weekend": all_dates.dayofweek.isin([5, 6])
})

# -------------------------------------------------------------------------
# 4. Save Processed Tables
# -------------------------------------------------------------------------
dim_customers.to_csv(PROCESSED_DIR / "dim_customers.csv", index=False)
dim_products.to_csv(PROCESSED_DIR / "dim_products.csv", index=False)
dim_dates.to_csv(PROCESSED_DIR / "dim_dates.csv", index=False)
fact_order_lines.to_csv(PROCESSED_DIR / "fact_order_lines.csv", index=False)

print("\n--- Processing Summary ---")
print(f"Total Clean Line Items:  {len(fact_order_lines):,}")
print(f"Total Unique Customers:   {len(dim_customers):,}")
print(f"Total Unique Products:    {len(dim_products):,}")
print(f"Returns / Cancellations:  {fact_order_lines['is_cancelled'].sum():,}")
print(f"Bulk Outlier Line Items:  {fact_order_lines['is_bulk_outlier'].sum():,}")
print(f"\nAll 4 Star Schema CSVs successfully generated in: {PROCESSED_DIR}")