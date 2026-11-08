import sqlite3
from pathlib import Path
import pandas as pd

# Define paths
BASE_DIR = Path(__file__).resolve().parent.parent
PROCESSED_DIR = BASE_DIR / "data" / "processed"
DB_PATH = PROCESSED_DIR / "retail_dw.db"

# Remove existing database file if recreating
if DB_PATH.exists():
    DB_PATH.unlink()

print(f"Connecting to database: {DB_PATH}")
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Enable foreign key constraint enforcement in SQLite
cursor.execute("PRAGMA foreign_keys = ON;")

# -------------------------------------------------------------------------
# 1. DDL Schema Definition (Star Schema)
# -------------------------------------------------------------------------
print("Creating Star Schema tables with DDL constraints...")

# Dimension: dim_customers
cursor.execute("""
CREATE TABLE IF NOT EXISTS dim_customers (
    customer_id TEXT PRIMARY KEY,
    signup_date TEXT NOT NULL,
    country TEXT NOT NULL
);
""")

# Dimension: dim_products
cursor.execute("""
CREATE TABLE IF NOT EXISTS dim_products (
    product_sku TEXT PRIMARY KEY,
    product_name TEXT NOT NULL,
    typical_unit_price REAL NOT NULL
);
""")

# Dimension: dim_dates
cursor.execute("""
CREATE TABLE IF NOT EXISTS dim_dates (
    date_key TEXT PRIMARY KEY,
    full_date TEXT NOT NULL,
    year INTEGER NOT NULL,
    quarter TEXT NOT NULL,
    month_number INTEGER NOT NULL,
    month_name TEXT NOT NULL,
    day_name TEXT NOT NULL,
    is_weekend INTEGER NOT NULL
);
""")

# Fact: fact_order_lines
cursor.execute("""
CREATE TABLE IF NOT EXISTS fact_order_lines (
    order_line_id TEXT PRIMARY KEY,
    invoice_no TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    product_sku TEXT NOT NULL,
    order_timestamp TEXT NOT NULL,
    order_date TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price REAL NOT NULL,
    line_total_revenue REAL NOT NULL,
    is_cancelled INTEGER NOT NULL,
    is_bulk_outlier INTEGER NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES dim_customers (customer_id),
    FOREIGN KEY (product_sku) REFERENCES dim_products (product_sku),
    FOREIGN KEY (order_date) REFERENCES dim_dates (date_key)
);
""")

conn.commit()

# -------------------------------------------------------------------------
# 2. Ingest Processed CSVs into SQLite
# -------------------------------------------------------------------------
tables_to_load = [
    ("dim_customers", PROCESSED_DIR / "dim_customers.csv"),
    ("dim_products", PROCESSED_DIR / "dim_products.csv"),
    ("dim_dates", PROCESSED_DIR / "dim_dates.csv"),
    ("fact_order_lines", PROCESSED_DIR / "fact_order_lines.csv")
]

for table_name, csv_file in tables_to_load:
    if not csv_file.exists():
        raise FileNotFoundError(f"Missing processed file: {csv_file}")
    
    print(f"Loading {table_name} from {csv_file.name}...")
    df = pd.read_csv(csv_file)
    
    # Append records directly into pre-defined DDL schema
    df.to_sql(table_name, conn, if_exists="append", index=False)
    
    # Row count verification
    cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
    row_count = cursor.fetchone()[0]
    print(f"  -> {table_name}: {row_count:,} records loaded.")

# -------------------------------------------------------------------------
# 3. Create Performance Indexes
# -------------------------------------------------------------------------
print("Creating indexes on foreign key columns...")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_fact_customer ON fact_order_lines(customer_id);")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_fact_product ON fact_order_lines(product_sku);")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_fact_date ON fact_order_lines(order_date);")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_fact_invoice ON fact_order_lines(invoice_no);")

conn.commit()
conn.close()

print("\nDatabase build complete! File saved at: data/processed/retail_dw.db")