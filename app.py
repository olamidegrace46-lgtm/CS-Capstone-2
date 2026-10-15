import json
import sqlite3

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st


@st.cache_resource
def get_connection():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    files = {
        "data/olist_orders_dataset.csv": "orders",
        "data/olist_order_items_dataset.csv": "order_items",
        "data/olist_order_reviews_dataset.csv": "reviews",
        "data/olist_customers_dataset.csv": "customers",
    }
    for path, table in files.items():
        pd.read_csv(path).to_sql(table, conn, index=False, if_exists="replace")
    return conn


conn = get_connection()

st.title("Customer Satisfaction Dashboard")

# Sidebar filters
year = st.sidebar.selectbox("Year", ["All", "2016", "2017", "2018"])
states = st.sidebar.multiselect("State", [])  # fill with state codes later
state_json = json.dumps(states)

# Headline KPIs (Q1)
q1 = """
SELECT COUNT(DISTINCT o.order_id) AS total_orders,
       COUNT(DISTINCT CASE WHEN o.order_status = 'delivered' THEN o.order_id END) AS delivered_orders,
       (SELECT ROUND(AVG(CAST(review_score AS REAL)), 2) FROM reviews) AS avg_review_score,
       SUM(CASE WHEN o.order_status = 'delivered'
                 AND o.order_delivered_customer_date > o.order_estimated_delivery_date
                THEN 1 ELSE 0 END) AS late_deliveries,
       ROUND(AVG(CASE WHEN o.order_status = 'delivered'
                       AND o.order_delivered_customer_date IS NOT NULL
                      THEN julianday(o.order_delivered_customer_date)
                         - julianday(o.order_purchase_timestamp) END), 2) AS avg_delivery_days
FROM orders o
WHERE (? = 'All' OR strftime('%Y', o.order_purchase_timestamp) = ?)
"""
kpi = pd.read_sql(q1, conn, params=(year, year)).iloc[0]

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total orders", f"{int(kpi.total_orders):,}")
col2.metric("Delivered", f"{int(kpi.delivered_orders):,}")
col3.metric("Avg review", f"{kpi.avg_review_score:.2f}")
col4.metric("Late deliveries", f"{int(kpi.late_deliveries):,}")
col5.metric("Avg delivery days", f"{kpi.avg_delivery_days:.2f}")

# Chart 1: review score distribution (Q2, not filterable)
q2 = """
SELECT CAST(review_score AS INTEGER) AS score,
       COUNT(*) AS reviews,
       ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM reviews), 1) AS pct
FROM reviews GROUP BY 1 ORDER BY 1
"""
df1 = pd.read_sql(q2, conn)
fig, ax = plt.subplots()
ax.bar(df1["score"].astype(str), df1["reviews"], color="#1F3A5F")
ax.set_title("Review score distribution")
ax.set_xlabel("Stars")
ax.set_ylabel("Reviews")
st.pyplot(fig)