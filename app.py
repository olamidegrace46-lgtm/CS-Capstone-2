import json
import sqlite3

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

BROWN = "#6B4226"
BUTTER = "#F3D96B"


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


def run(query, params=()):
    return pd.read_sql(query, conn, params=params)


# ---------- Verified queries ----------

Q1 = """
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

Q2 = """
SELECT CAST(review_score AS INTEGER) AS score,
       COUNT(*) AS reviews,
       ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM reviews), 1) AS pct
FROM reviews GROUP BY 1 ORDER BY 1
"""

Q3 = """
SELECT strftime('%Y-%m', o.order_purchase_timestamp) AS month,
       COUNT(*) AS reviews,
       ROUND(AVG(CAST(r.review_score AS REAL)), 3) AS avg_score
FROM orders o
JOIN reviews r ON o.order_id = r.order_id
WHERE (? = 'All' OR strftime('%Y', o.order_purchase_timestamp) = ?)
GROUP BY month ORDER BY month
"""

Q4 = """
SELECT c.customer_state AS state,
       COUNT(DISTINCT o.order_id) AS orders,
       ROUND(AVG(CAST(r.review_score AS REAL)), 3) AS avg_score
FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
JOIN reviews r ON o.order_id = r.order_id
WHERE (? = '[]' OR c.customer_state IN (SELECT value FROM json_each(?)))
GROUP BY state ORDER BY orders DESC LIMIT 10
"""

Q5 = """
SELECT c.customer_state AS state,
       COUNT(DISTINCT o.order_id) AS delivered,
       SUM(CASE WHEN o.order_delivered_customer_date > o.order_estimated_delivery_date
                THEN 1 ELSE 0 END) AS late
FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
WHERE o.order_status = 'delivered'
  AND o.order_delivered_customer_date IS NOT NULL
  AND (? = '[]' OR c.customer_state IN (SELECT value FROM json_each(?)))
GROUP BY state ORDER BY delivered DESC LIMIT 5
"""

Q6 = """
SELECT CASE WHEN o.order_delivered_customer_date <= o.order_estimated_delivery_date
            THEN 'On Time' ELSE 'Late' END AS delivery_status,
       COUNT(DISTINCT o.order_id) AS orders,
       ROUND(AVG(CAST(r.review_score AS REAL)), 2) AS avg_score,
       ROUND(AVG(julianday(o.order_delivered_customer_date)
                 - julianday(o.order_purchase_timestamp)), 2) AS avg_delivery_days
FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
JOIN reviews r ON o.order_id = r.order_id
WHERE o.order_status = 'delivered'
  AND o.order_delivered_customer_date IS NOT NULL
  AND (? = '[]' OR c.customer_state IN (SELECT value FROM json_each(?)))
GROUP BY 1 ORDER BY avg_score DESC
"""

# ---------- Sidebar filters ----------

all_states = run("SELECT DISTINCT customer_state FROM customers ORDER BY 1")["customer_state"].tolist()
year = st.sidebar.selectbox("Year", ["All", "2016", "2017", "2018"])
states = st.sidebar.multiselect("State", all_states)
state_json = json.dumps(states)  # empty list means "no state filter"


# ---------- Chart functions ----------

def kpi_row(year):
    kpi = run(Q1, (year, year)).iloc[0]
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total orders", f"{int(kpi.total_orders):,}")
    c2.metric("Delivered", f"{int(kpi.delivered_orders):,}")
    c3.metric("Avg review", f"{kpi.avg_review_score:.2f}")
    c4.metric("Late deliveries", f"{int(kpi.late_deliveries):,}")
    c5.metric("Avg delivery days", f"{kpi.avg_delivery_days:.2f}")


def chart_review_distribution():
    df = run(Q2)
    fig, ax = plt.subplots(figsize=(6, 4))
    bars = ax.bar(df["score"].astype(str), df["reviews"], color=BROWN)
    for bar, pct in zip(bars, df["pct"]):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                f"{pct}%", ha="center", va="bottom")
    ax.set_title("Review score distribution")
    ax.set_xlabel("Stars")
    ax.set_ylabel("Reviews")
    st.pyplot(fig)


def chart_monthly_score(year):
    df = run(Q3, (year, year))
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(df["month"], df["avg_score"], marker="o", color=BROWN, markerfacecolor=BUTTER)
    ax.set_title("Monthly average review score\n(2016 is a partial year with few reviews)")
    ax.set_ylabel("Average score")
    ax.set_ylim(1, 5)
    ax.tick_params(axis="x", rotation=90)
    plt.tight_layout()
    st.pyplot(fig)


def chart_state_scores(state_json):
    df = run(Q4, (state_json, state_json))
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.barh(df["state"], df["avg_score"], color=BROWN)
    ax.invert_yaxis()
    ax.set_title("Average review score by state (top 10 by orders)")
    ax.set_xlabel("Average review score")
    ax.set_xlim(3, 4.5)
    plt.tight_layout()
    st.pyplot(fig)


def chart_ontime_late(state_json):
    df = run(Q5, (state_json, state_json))
    df["on_time"] = df["delivered"] - df["late"]
    x = range(len(df))
    w = 0.38
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar([i - w / 2 for i in x], df["on_time"], w, label="On time", color=BUTTER)
    ax.bar([i + w / 2 for i in x], df["late"], w, label="Late", color=BROWN)
    ax.set_xticks(list(x))
    ax.set_xticklabels(df["state"])
    ax.set_title("On-time vs late delivery by state (top 5)")
    ax.set_ylabel("Delivered orders")
    ax.legend()
    plt.tight_layout()
    st.pyplot(fig)


def chart_punctuality(state_json):
    df = run(Q6, (state_json, state_json))
    fig, ax = plt.subplots(figsize=(6, 4))
    colors = [BUTTER if s == "On Time" else BROWN for s in df["delivery_status"]]
    bars = ax.bar(df["delivery_status"], df["avg_score"], color=colors)
    for bar, (_, row) in zip(bars, df.iterrows()):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                f"{row['avg_score']:.2f} stars\n{row['avg_delivery_days']:.2f} days",
                ha="center", va="bottom")
    ax.set_ylim(0, 5)
    ax.set_title("Delivery punctuality vs satisfaction")
    ax.set_ylabel("Average review score")
    plt.tight_layout()
    st.pyplot(fig)


# ---------- Layout: three tabs ----------

st.title("Customer Satisfaction Dashboard")

tab_overview, tab_theme, tab_detail = st.tabs(["Overview", "Customer Satisfaction", "Detail & Method"])

with tab_overview:
    kpi_row(year)
    chart_review_distribution()

with tab_theme:
    chart_monthly_score(year)
    chart_state_scores(state_json)
    chart_ontime_late(state_json)

with tab_detail:
    chart_punctuality(state_json)
    st.caption(
        "Late counts on this chart include only reviewed orders (7,661). "
        "The headline KPI counts all late delivered orders (7,826)."
    )
    st.caption(
        "2016 and 2018 are partial years. November 2016 has no orders, "
        "so year-over-year comparisons need that flagged."
    )