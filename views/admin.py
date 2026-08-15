from datetime import date, timedelta
import pandas as pd
from sqlalchemy import create_engine, text
import streamlit as st

BRAND_NAME = "TASTY India"
ADMIN_PIN = "5678"


# Database Connection
@st.cache_resource
def get_engine():
  db_url = st.secrets["postgres"]["url"]
  return create_engine(db_url, pool_pre_ping=True)


engine = get_engine()


def load_menu():
  with engine.connect() as conn:
    return pd.read_sql(
        "SELECT id, category, item_name, price, daily_cap, active FROM menu"
        " ORDER BY id ASC",
        conn,
    )


def load_orders():
  query = """
        SELECT 
            o.order_id,
            o.created_at,
            o.pickup_date,
            o.order_type,
            o.slot,
            o.flat_no,
            o.name,
            o.phone,
            o.total_inr,
            o.utr_ref,
            o.status,
            STRING_AGG(oi.item_name || ' x' || oi.quantity, ', ') AS items_ordered
        FROM orders o
        LEFT JOIN order_items oi ON o.order_id = oi.order_id
        GROUP BY o.order_id, o.created_at, o.pickup_date, o.order_type, o.slot, o.flat_no, o.name, o.phone, o.total_inr, o.utr_ref, o.status
        ORDER BY o.created_at DESC;
    """
  with engine.connect() as conn:
    return pd.read_sql(query, conn)


def load_kitchen_summary(target_date):
  query = """
        SELECT 
            oi.item_name AS "Menu Item",
            SUM(oi.quantity) AS "Batch Prep Quantity"
        FROM order_items oi
        JOIN orders o ON oi.order_id = o.order_id
        WHERE o.pickup_date = :target_date
        GROUP BY oi.item_name
        ORDER BY "Batch Prep Quantity" DESC;
    """
  with engine.connect() as conn:
    return pd.read_sql(text(query), conn, params={"target_date": target_date})


st.title(f"🔐 {BRAND_NAME} — Admin & Kitchen Portal")

admin_pin = st.text_input("Enter Admin PIN to Unlock", type="password")

if admin_pin == ADMIN_PIN:
  admin_tab1, admin_tab2 = st.tabs(
      ["👨‍🍳 Kitchen Prep & Live Queue", "✏️ Menu & Pricing Manager"]
  )

  with admin_tab1:
    filter_date = st.date_input(
        "Filter Orders By Date",
        value=date.today() + timedelta(days=1),
    )

    orders_df = load_orders()
    daily_orders = (
        orders_df[orders_df["pickup_date"].astype(str) == str(filter_date)]
        if not orders_df.empty
        else pd.DataFrame()
    )

    m1, m2, m3 = st.columns(3)
    m1.metric(
        "Total Orders", len(daily_orders) if not daily_orders.empty else 0
    )
    m2.metric(
        "Total Revenue (₹)",
        daily_orders["total_inr"].sum() if not daily_orders.empty else 0,
    )
    m3.metric(
        "Dishes Count",
        daily_orders["items_ordered"].count() if not daily_orders.empty else 0,
    )

    st.markdown("---")
    st.subheader(f"🥣 Batch Cooking Requirements for {filter_date}")
    summary_df = load_kitchen_summary(filter_date)

    if not summary_df.empty:
      st.dataframe(summary_df, hide_index=True, use_container_width=True)
    else:
      st.info(f"No orders registered for {filter_date} yet.")

    st.subheader("📋 Order Tickets")
    if not daily_orders.empty:
      st.dataframe(
          daily_orders[[
              "order_id",
              "slot",
              "flat_no",
              "name",
              "phone",
              "items_ordered",
              "total_inr",
              "utr_ref",
              "status",
          ]],
          hide_index=True,
          use_container_width=True,
      )
    else:
      st.write("No ticket records for this date.")

  with admin_tab2:
    st.subheader("✏️ Live Menu & Stock Controller")
    current_menu = load_menu()

    edited_menu = st.data_editor(
        current_menu,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "id": st.column_config.NumberColumn("ID", disabled=True),
            "category": st.column_config.SelectboxColumn(
                "Category",
                options=[
                    "Breakfast",
                    "Lunch",
                    "Snacks",
                    "Dinner",
                    "Beverages",
                ],
                required=True,
            ),
            "item_name": st.column_config.TextColumn(
                "Item Name", required=True
            ),
            "price": st.column_config.NumberColumn(
                "Price (₹)", min_value=1, format="₹%d"
            ),
            "daily_cap": st.column_config.NumberColumn(
                "Stock Limit", min_value=1
            ),
            "active": st.column_config.CheckboxColumn(
                "Active?", default=True
            ),
        },
    )

    if st.button("💾 Save Menu Changes", type="primary"):
      try:
        with engine.begin() as db_conn:
          db_conn.execute(text("TRUNCATE TABLE menu RESTART IDENTITY CASCADE;"))
          for _, row in edited_menu.iterrows():
            if pd.notna(row["item_name"]) and str(row["item_name"]).strip():
              insert_item = text("""
                  INSERT INTO menu (category, item_name, price, daily_cap, active)
                  VALUES (:category, :item_name, :price, :daily_cap, :active)
              """)
              db_conn.execute(
                  insert_item,
                  {
                      "category": row["category"],
                      "item_name": row["item_name"],
                      "price": int(row["price"]),
                      "daily_cap": (
                          int(row["daily_cap"])
                          if pd.notna(row["daily_cap"])
                          else 50
                      ),
                      "active": bool(row["active"]),
                  },
              )
        st.success("Menu updated in Neon DB successfully!")
        st.rerun()
      except Exception as e:
        st.error(f"Error updating menu: {e}")

elif admin_pin:
  st.error("Incorrect PIN. Access Denied.")

# At the bottom/main section of views/admin.py:
def render():
    # Place all your admin PIN check and kitchen dashboards here
    ...
