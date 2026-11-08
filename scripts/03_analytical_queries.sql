-- =========================================================================
-- Stage 3: Analytical SQL Queries (retail_dw.db)
-- =========================================================================

-- -------------------------------------------------------------------------
-- Query 1: Customer Repeat Purchase Behavior & Reorder Lag Time
-- Objective: Calculate the days elapsed between consecutive purchases per customer
-- -------------------------------------------------------------------------
WITH UniqueCustomerOrders AS (
    SELECT DISTINCT
        customer_id,
        invoice_no,
        order_date
    FROM fact_order_lines
    WHERE is_cancelled = 0
),
OrderIntervals AS (
    SELECT 
        customer_id,
        invoice_no,
        order_date,
        LAG(order_date, 1) OVER (
            PARTITION BY customer_id 
            ORDER BY order_date ASC
        ) AS previous_order_date
    FROM UniqueCustomerOrders
)
SELECT 
    customer_id,
    invoice_no,
    order_date,
    previous_order_date,
    ROUND(JULIANDAY(order_date) - JULIANDAY(previous_order_date), 0) AS days_since_last_order
FROM OrderIntervals
WHERE previous_order_date IS NOT NULL
ORDER BY customer_id, order_date;


-- -------------------------------------------------------------------------
-- Query 2: RFM Customer Segmentation (Recency, Frequency, Monetary)
-- Objective: Classify customers into tiers using NTILE() window distributions
-- -------------------------------------------------------------------------
WITH CustomerMetrics AS (
    SELECT 
        customer_id,
        MAX(order_date) AS last_purchase_date,
        COUNT(DISTINCT invoice_no) AS total_orders,
        SUM(line_total_revenue) AS monetary_value
    FROM fact_order_lines
    WHERE is_cancelled = 0
    GROUP BY customer_id
),
ReferenceDate AS (
    -- Anchor to the latest transaction date in the entire dataset
    SELECT MAX(order_date) AS max_date FROM fact_order_lines
),
RFM_Scores AS (
    SELECT 
        m.customer_id,
        ROUND(JULIANDAY(r.max_date) - JULIANDAY(m.last_purchase_date), 0) AS recency_days,
        m.total_orders AS frequency,
        ROUND(m.monetary_value, 2) AS monetary,
        NTILE(4) OVER (ORDER BY JULIANDAY(r.max_date) - JULIANDAY(m.last_purchase_date) DESC) AS r_score,
        NTILE(4) OVER (ORDER BY m.total_orders ASC) AS f_score,
        NTILE(4) OVER (ORDER BY m.monetary_value ASC) AS m_score
    FROM CustomerMetrics m
    CROSS JOIN ReferenceDate r
)
SELECT 
    customer_id,
    recency_days,
    frequency,
    monetary,
    r_score,
    f_score,
    m_score,
    (r_score + f_score + m_score) AS rfm_composite_score,
    CASE 
        WHEN (r_score + f_score + m_score) >= 10 THEN 'Champions / VIP'
        WHEN (r_score + f_score + m_score) >= 7  THEN 'Loyal Customers'
        WHEN r_score <= 2 AND f_score >= 3       THEN 'At Risk (High Value Inactive)'
        ELSE 'Standard / Low Engagement'
    END AS customer_tier
FROM RFM_Scores
ORDER BY rfm_composite_score DESC;


-- -------------------------------------------------------------------------
-- Query 3: Monthly Customer Acquisition & Cohort Retention Setup
-- Objective: Map acquisition cohorts and subsequent order months
-- -------------------------------------------------------------------------
WITH CustomerFirstPurchase AS (
    SELECT 
        customer_id,
        MIN(order_date) AS first_order_date,
        SUBSTR(MIN(order_date), 1, 7) AS cohort_month
    FROM fact_order_lines
    WHERE is_cancelled = 0
    GROUP BY customer_id
),
CustomerActivity AS (
    SELECT DISTINCT
        f.customer_id,
        c.cohort_month,
        SUBSTR(f.order_date, 1, 7) AS activity_month,
        (CAST(SUBSTR(f.order_date, 1, 4) AS INT) - CAST(SUBSTR(c.cohort_month, 1, 4) AS INT)) * 12 +
        (CAST(SUBSTR(f.order_date, 6, 2) AS INT) - CAST(SUBSTR(c.cohort_month, 6, 2) AS INT)) AS month_number
    FROM fact_order_lines f
    JOIN CustomerFirstPurchase c ON f.customer_id = c.customer_id
    WHERE f.is_cancelled = 0
)
SELECT 
    cohort_month,
    month_number,
    COUNT(DISTINCT customer_id) AS active_retained_customers
FROM CustomerActivity
GROUP BY cohort_month, month_number
ORDER BY cohort_month, month_number;


-- -------------------------------------------------------------------------
-- Query 4: Return & Cancellation Revenue Drain by Country
-- Objective: Measure gross revenue lost to cancelled orders
-- -------------------------------------------------------------------------
SELECT 
    c.country,
    COUNT(DISTINCT f.invoice_no) AS total_invoices,
    SUM(CASE WHEN f.is_cancelled = 0 THEN f.line_total_revenue ELSE 0 END) AS net_realized_revenue,
    ABS(SUM(CASE WHEN f.is_cancelled = 1 THEN f.line_total_revenue ELSE 0 END)) AS cancelled_revenue_loss,
    ROUND(
        ABS(SUM(CASE WHEN f.is_cancelled = 1 THEN f.line_total_revenue ELSE 0 END)) * 100.0 /
        NULLIF(SUM(CASE WHEN f.is_cancelled = 0 THEN f.line_total_revenue ELSE 0 END), 0),
        2
    ) AS return_revenue_drag_pct
FROM fact_order_lines f
JOIN dim_customers c ON f.customer_id = c.customer_id
GROUP BY c.country
HAVING total_invoices >= 20
ORDER BY return_revenue_drag_pct DESC;