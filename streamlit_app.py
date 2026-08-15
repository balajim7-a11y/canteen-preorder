import io
import urllib.parse
from datetime import date, datetime, timedelta
import pandas as pd
import qrcode
from sqlalchemy import create_engine, text
import streamlit as st

# ====================================================
# CONFIGURATION
# ====================================================
UPI_ID = "yourfriend@upi"  # Replace with actual UPI ID (e.g. 9876543210@paytm)
PAYEE_NAME = "Clubhouse Canteen"
ADMIN_PIN = "5678"

st.set_page_config(
    page_title="Clubhouse Canteen", page_icon="🍲", layout="centered"
)


# --- Database Connection (Neon PostgreSQL) ---
@st.cache_resource
def get_engine():
  db_url = st.secrets["postgres"]["url"]
  return create_engine(db_url, pool_pre_ping=True)


engine = get_engine()


# Helper: Load Menu
def load_menu():
  with engine.connect() as conn:
    return pd.read_sql(
        "SELECT id, category, item_name, price, daily_cap, active FROM menu"
        " ORDER BY id ASC",
        conn,
    )


# Helper: Load Orders
def load_orders():
  with engine.connect() as conn:
    return pd.read_sql(
        "SELECT * FROM orders ORDER BY created_at DESC", conn
    )


# Helper: Generate UPI URL & QR Code
def create_upi_intent(
    upi_id: str, payee_name: str, amount: float, order_id: str
):
  encoded_name = urllib.parse.quote(payee_name)
  upi_url = f"upi://pay?pa={upi_id}&pn={encoded_name}&am={amount:.2f}&tn=Order_{order_id}&cu=INR"
  qr = qrcode.make(upi_url)
  buf = io.BytesIO()
  qr.save(buf, format="PNG")
  return upi_url, buf.getvalue()


tab_order, tab_kitchen = st.tabs(
    ["🛒 Place Order", "👨‍🍳 Kitchen & Menu Management"]
)

# ====================================================
# TAB 1: RESIDENT ORDERING (NOW & LATER)
# ====================================================
with tab_order:
  st.header("Clubhouse Canteen")

  order_type = st.radio(
      "When do you want your food?",
      ["Today (Order Now)", "Tomorrow (Pre-Order)"],
      horizontal=True,
  )

  if order_type == "Today (Order Now)":
    selected_date = date.today()
    slots = [
        "Immediate / ASAP (15-20 mins)",
        "Lunch: 1:00 PM - 2:00 PM",
        "Snacks: 4:30 PM - 6:00 PM",
        "Dinner: 7:30 PM - 9:00 PM",
    ]
  else:
    selected_date = date.today() + timedelta(days=1)
    slots = [
        "Breakfast: 7:30 AM - 8:15 AM",
        "Breakfast: 8:15 AM - 9:00 AM",
        "Lunch: 12:30 PM - 1:30 PM",
        "Lunch: 1:30 PM - 2:15 PM",
        "Dinner: 7:30 PM - 8:30 PM",
    ]

  st.caption(
      f"📅 Selected Pickup Date: **{selected_date.strftime('%A, %d %B %Y')}**"
  )

  with st.expander("Resident & Delivery Details", expanded=True):
    c1, c2 = st.columns(2)
    flat_no = c1.text_input("Flat / Door Number (e.g. A-402)*")
    resident_name = c2.text_input("Your Name*")
    phone = c1.text_input("Mobile Number*")
    slot = c2.selectbox("Pickup Time Slot*", slots)

  st.subheader("Menu Items")
  try:
    menu_df = load_menu()
    active_items = menu_df[menu_df["active"] == True]
  except Exception as e:
    st.error(f"Error connecting to database: {e}")
    active_items = pd.DataFrame()

  order_items = {}
  total_bill = 0

  if not active_items.empty:
    categories = active_items["category"].unique()
    for cat in categories:
      st.markdown(f"#### {cat}")
      cat_items = active_items[active_items["category"] == cat]

      for _, row in cat_items.iterrows():
        c_name, c_price, c_qty = st.columns([3, 1, 2])
        c_name.write(f"**{row['item_name']}**")
        c_price.write(f"₹{row['price']}")
        max_cap = int(row["daily_cap"]) if pd.notna(row["daily_cap"]) else 50
        qty = c_qty.number_input(
            "Qty",
            min_value=0,
            max_value=max_cap,
            value=0,
            key=f"item_{row['id']}",
        )
        if qty > 0:
          order_items[row["item_name"]] = qty
          total_bill += qty * int(row["price"])
  else:
    st.info("No active menu items available at the moment.")

  st.divider()
  st.markdown(f"### Total Amount: **₹{total_bill}**")

  if total_bill > 0 and flat_no and resident_name and phone:
    order_id = f"ORD-{datetime.now().strftime('%H%M%S')}"
    upi_url, qr_bytes = create_upi_intent(
        UPI_ID, PAYEE_NAME, total_bill, order_id
    )

    st.subheader("Payment")
    st.link_button(
        f"👉 Tap to Pay ₹{total_bill} via UPI App",
        upi_url,
        type="primary",
        use_container_width=True,
    )

    with st.expander("Or scan QR Code to pay", expanded=False):
      st.image(qr_bytes, width=180)
      st.caption(f"UPI ID: `{UPI_ID}` | Ref Note: `Order_{order_id}`")

    utr_input = st.text_input("UPI Reference ID / UTR (Optional)")

    if st.button(
        "Confirm & Submit Order", type="primary", use_container_width=True
    ):
      items_str = ", ".join([f"{k} x{v}" for k, v in order_items.items()])
      insert_query = text("""
                INSERT INTO orders (order_id, pickup_date, order_type, slot, flat_no, name, phone, items, total_inr, utr_ref, status)
                VALUES (:order_id, :pickup_date, :order_type, :slot, :flat_no, :name, :phone, :items, :total_inr, :utr_ref, :status)
            """)

      params = {
          "order_id": order_id,
          "pickup_date": selected_date,
          "order_type": "Now" if "Today" in order_type else "Pre-Order",
          "slot": slot,
          "flat_no": flat_no,
          "name": resident_name,
          "phone": phone,
          "items": items_str,
          "total_inr": total_bill,
          "utr_ref": utr_input if utr_input else "N/A",
          "status": "Confirmed",
      }

      try:
        with engine.begin() as db_conn:
          db_conn.execute(insert_query, params)
        st.success(f"Order #{order_id} placed successfully!")
        st.balloons()
      except Exception as ex:
        st.error(f"Error saving order: {ex}")
  elif total_bill > 0:
    st.info(
        "Please fill in Flat Number, Name, and Mobile Number to place your"
        " order."
    )

# ====================================================
# TAB 2: KITCHEN DASHBOARD & IN-APP MENU EDITOR
# ====================================================
with tab_kitchen:
  st.header("Kitchen & Menu Control")
  admin_pin = st.text_input("Enter Admin PIN", type="password")

  if admin_pin == ADMIN_PIN:
    kitchen_tab1, kitchen_tab2 = st.tabs(
        ["📋 Active Orders & Kitchen Prep", "✏️ Edit / Add Menu Items"]
    )

    # SUB-TAB A: ORDERS DASHBOARD
    with kitchen_tab1:
      try:
        orders_df = load_orders()
        if orders_df.empty:
          st.info("No orders recorded yet.")
        else:
          filter_date = st.date_input(
              "Filter Orders By Date", value=date.today()
          )
          daily_orders = orders_df[
              orders_df["pickup_date"].astype(str) == str(filter_date)
          ]

          st.subheader(f"Quantities to Prepare for {filter_date}")

          item_counts = {}
          for entry in daily_orders["items"].dropna():
            for item in str(entry).split(", "):
              if " x" in item:
                name, count = item.rsplit(" x", 1)
                item_counts[name] = item_counts.get(name, 0) + int(count)

          if item_counts:
            summary_df = pd.DataFrame(
                list(item_counts.items()), columns=["Item", "Total Quantity"]
            )
            st.dataframe(summary_df, use_container_width=True)
          else:
            st.write("No items ordered for this date yet.")

          st.subheader("Order Details")
          st.dataframe(daily_orders, use_container_width=True)
      except Exception as e:
        st.error(f"Error reading orders: {e}")

    # SUB-TAB B: IN-APP MENU EDITOR
    with kitchen_tab2:
      st.subheader("Manage Menu Items & Prices")
      st.caption(
          "Edit items directly below, add new rows at the bottom, or toggle"
          " availability."
      )

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
                  "Available?", default=True
              ),
          },
      )

      if st.button("💾 Save Menu Changes to Neon DB", type="primary"):
        try:
          with engine.begin() as db_conn:
            db_conn.execute(text("TRUNCATE TABLE menu RESTART IDENTITY;"))
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
    st.error("Incorrect PIN")
