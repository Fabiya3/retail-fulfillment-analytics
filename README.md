# Multi-Channel Retail & Fulfillment Analytics Platform

An end-to-end business intelligence and data warehousing project built on the Online Retail II transactional dataset (~540k records).

## Architecture
- **ETL Layer:** Python 3.13, Pandas (vectorized data hygiene, downcasting, IQR outlier screening)
- **Database Layer:** SQLite relational data warehouse (`retail_dw.db`) structured in a strict Star Schema
- **Analytics Layer:** SQL models using window functions (`LAG`, `NTILE`), cohort retention, and RFM segmentation
- **BI Layer:** Power BI executive dashboard with dynamic DAX financial measures and VertiPaq time intelligence

## Data Model (Star Schema)
- `fact_order_lines` (Fact): Granular line-item orders with revenue, return flags, and foreign keys
- `dim_customers` (Dimension): Unique customer IDs and country regions
- `dim_products` (Dimension): Product SKUs, descriptions, and unit prices
- `dim_dates` (Dimension): Contiguous daily calendar table

## Key Business Insights
- Isolated return and cancellation drag across international markets.
- Tracked reorder intervals and segmented top customers into VIP tiers using RFM scoring.
- Built executive reporting for revenue throughput, average order values, and YoY growth.
