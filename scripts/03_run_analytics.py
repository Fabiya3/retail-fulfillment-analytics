import sqlite3
from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "processed" / "retail_dw.db"
SQL_FILE = BASE_DIR / "scripts" / "03_analytical_queries.sql"
OUTPUT_DIR = BASE_DIR / "data" / "processed" / "reports"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

if not DB_PATH.exists():
    raise FileNotFoundError(f"Database not found at: {DB_PATH}")

conn = sqlite3.connect(DB_PATH)

print("Reading SQL scripts...")
with open(SQL_FILE, "r") as f:
    sql_script = f.read()

# Separate statements by double semicolon or custom markers
queries = {
    "repeat_purchase_intervals": """
        WITH UniqueCustomerOrders AS (
            SELECT DISTINCT customer_id, invoice_no, order_date
            FROM fact_order_lines WHERE is_cancelled = 0
        ),
        OrderIntervals AS (
            SELECT customer_id, invoice_no, order_date,
                   LAG(order_date, 1) OVER (PARTITION BY customer_id ORDER BY order_date ASC) AS previous_order_date
            FROM UniqueCustomerOrders
        )
        SELECT customer_id, invoice_no, order_date, previous_order_date,
               ROUND(JULIANDAY(order_date) - JULIANDAY(previous_order_date), 0) AS days_since_last_order
        FROM OrderIntervals WHERE previous_order_date IS NOT NULL;
    """,
    "rfm_segmentation": """
        WITH CustomerMetrics AS (
            SELECT customer_id, MAX(order_date) AS last_purchase_date,
                   COUNT(DISTINCT invoice_no) AS total_orders,
                   SUM(line_total_revenue) AS monetary_value
            FROM fact_order_lines WHERE is_cancelled = 0
            GROUP BY customer_id
        ),
        ReferenceDate AS (SELECT MAX(order_date) AS max_date FROM fact_order_lines),
        RFM_Scores AS (
            SELECT m.customer_id,
                   ROUND(JULIANDAY(r.max_date) - JULIANDAY(m.last_purchase_date), 0) AS recency_days,
                   m.total_orders AS frequency,
                   ROUND(m.monetary_value, 2) AS monetary,
                   NTILE(4) OVER (ORDER BY JULIANDAY(r.max_date) - JULIANDAY(m.last_purchase_date) DESC) AS r_score,
                   NTILE(4) OVER (ORDER BY m.total_orders ASC) AS f_score,
                   NTILE(4) OVER (ORDER BY m.monetary_value ASC) AS m_score
            FROM CustomerMetrics m CROSS JOIN ReferenceDate r
        )
        SELECT customer_id, recency_days, frequency, monetary, r_score, f_score, m_score,
               (r_score + f_score + m_score) AS rfm_composite_score,
               CASE 
                   WHEN (r_score + f_score + m_score) >= 10 THEN 'Champions / VIP'
                   WHEN (r_score + f_score + m_score) >= 7  THEN 'Loyal Customers'
                   WHEN r_score <= 2 AND f_score >= 3       THEN 'At Risk (High Value Inactive)'
                   ELSE 'Standard / Low Engagement'
               END AS customer_tier
        FROM RFM_Scores;
    """,
    "cohort_retention": """
        WITH CustomerFirstPurchase AS (
            SELECT customer_id, MIN(order_date) AS first_order_date,
                   SUBSTR(MIN(order_date), 1, 7) AS cohort_month
            FROM fact_order_lines WHERE is_cancelled = 0
            GROUP BY customer_id
        ),
        CustomerActivity AS (
            SELECT DISTINCT f.customer_id, c.cohort_month,
                   (CAST(SUBSTR(f.order_date, 1, 4) AS INT) - CAST(SUBSTR(c.cohort_month, 1, 4) AS INT)) * 12 +
                   (CAST(SUBSTR(f.order_date, 6, 2) AS INT) - CAST(SUBSTR(c.cohort_month, 6, 2) AS INT)) AS month_number
            FROM fact_order_lines f
            JOIN CustomerFirstPurchase c ON f.customer_id = c.customer_id
            WHERE f.is_cancelled = 0
        )
        SELECT cohort_month, month_number, COUNT(DISTINCT customer_id) AS active_retained_customers
        FROM CustomerActivity
        GROUP BY cohort_month, month_number
        ORDER BY cohort_month, month_number;
    """,
    "country_cancellation_drag": """
        SELECT c.country,
               COUNT(DISTINCT f.invoice_no) AS total_invoices,
               ROUND(SUM(CASE WHEN f.is_cancelled = 0 THEN f.line_total_revenue ELSE 0 END), 2) AS net_realized_revenue,
               ROUND(ABS(SUM(CASE WHEN f.is_cancelled = 1 THEN f.line_total_revenue ELSE 0 END)), 2) AS cancelled_revenue_loss,
               ROUND(ABS(SUM(CASE WHEN f.is_cancelled = 1 THEN f.line_total_revenue ELSE 0 END)) * 100.0 /
                     NULLIF(SUM(CASE WHEN f.is_cancelled = 0 THEN f.line_total_revenue ELSE 0 END), 0), 2) AS return_revenue_drag_pct
        FROM fact_order_lines f
        JOIN dim_customers c ON f.customer_id = c.customer_id
        GROUP BY c.country
        HAVING total_invoices >= 20
        ORDER BY return_revenue_drag_pct DESC;
    """
}

for report_name, query in queries.items():
    print(f"Executing query: {report_name}...")
    df_result = pd.read_sql_query(query, conn)
    export_path = OUTPUT_DIR / f"{report_name}.csv"
    df_result.to_csv(export_path, index=False)
    print(f"  -> Saved {len(df_result):,} rows to {export_path.name}")

conn.close()
print("\nAnalytical execution complete! Output files ready in data/processed/reports/")