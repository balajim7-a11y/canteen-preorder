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
BRAND_NAME = "TASTY India"
BRAND_TAGLINE = "Tasty South grp"
UPI_ID = "yourfriend@upi"  # Replace with actual UPI VPA (e.g. 9876543210@paytm)
MIN_DELIVERY_AMOUNT = 150


# ====================================================
# DATABASE & CACHING
# ====================================================
@st.cache_resource
def get_engine():
  db_url = st.secrets["postgres"]["url"]
  return create_engine(
      db_url,
      pool_size=5,
      max_overflow=10,
      pool_recycle=1800,
      pool_pre_ping=True,
  )


engine = get_engine()


# Cached menu loader (60-second TTL for low latency)
@st.cache_data(ttl=60)
def load_menu():
  with engine.connect() as conn:
    return pd.read_sql(
        "SELECT id, category, item_name, price, daily_cap, active FROM menu"
        " ORDER BY id ASC",
        conn,
    )


# Helper: Generate UPI Intent Link and QR Code
def create_upi_intent(
    upi_id: str, payee_name: str, amount: float, order_id: str
):
  encoded_name = urllib.parse.quote(payee_name)
  upi_url = f"upi://pay?pa={upi_id}&pn={encoded_name}&am={amount:.2f}&tn=Order_{order_id}&cu=INR"
  qr = qrcode.make(upi_url)
  buf = io.BytesIO()
  qr.save(buf, format="PNG")
  return upi_url, buf.getvalue()


# ====================================================
# BRAND HEADER
# ====================================================
col_logo, col_head = st.columns([1, 4])
with col_logo:
  try:
    st.image("logo.png", width=110)
  except Exception:
    st.write("🍛")
with col_head:
  st.title(f"{BRAND_NAME}")
  st.caption(f"✨ *{BRAND_TAGLINE}* | Clubhouse Cafeteria")

# ====================================================
# TIMELINE SELECTION
# ====================================================
col_t1, col_t2 = st.columns([1, 1])
with col_t1:
  order_type = st.segmented_control(
      "Order Timeline",
      ["Today (Instant / Current)", "Tomorrow (Pre-Order)"],
      default="Tomorrow (Pre-Order)",
  )

if order_type == "Today (Instant / Current)":
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

with col_t2:
  st.markdown(
      f"📅 **Selected Date:** `{selected_date.strftime('%A, %d %B %Y')}`"
  )

st.markdown("---")

# ====================================================
# MENU SELECTION
# ====================================================
st.subheader("📋 Select Dishes")

try:
  menu_df = load_menu()
  active_items = menu_df[menu_df["active"] == True]
except Exception as e:
  st.error(f"Unable to load menu: {e}")
  active_items = pd.DataFrame()

order_items = []
total_bill = 0

if not active_items.empty:
  categories = active_items["category"].unique()
  tabs = st.tabs([f"🍴 {cat}" for cat in categories])

  for tab, cat in zip(tabs, categories):
    with tab:
      cat_items = active_items[active_items["category"] == cat]
      for _, row in cat_items.iterrows():
        c_info, c_price, c_qty = st.columns([4, 2, 2])
        with c_info:
          st.markdown(f"**{row['item_name']}**")
        with c_price:
          st.markdown(f"**₹{row['price']}**")
        with c_qty:
          max_cap = int(row["daily_cap"]) if pd.notna(row["daily_cap"]) else 50
          qty = st.number_input(
              "Quantity",
              min_value=0,
              max_value=max_cap,
              value=0,
              key=f"qty_{row['id']}",
              label_visibility="collapsed",
          )

        if qty > 0:
          subtotal = qty * int(row["price"])
          order_items.append({
              "item_id": int(row["id"]),
              "item_name": str(row["item_name"]),
              "quantity": int(qty),
              "unit_price": int(row["price"]),
              "subtotal": int(subtotal),
          })
          total_bill += subtotal
        st.divider()

# ====================================================
# DELIVERY LOGIC (>= 150 ELIGIBILITY)
# ====================================================
if total_bill >= MIN_DELIVERY_AMOUNT:
  st.success(
      "🛵 **Eligible for FREE Doorstep Delivery!** (Order is ₹150 or more)"
  )
elif total_bill > 0:
  diff = MIN_DELIVERY_AMOUNT - total_bill
  st.info(
      f"💡 Add **₹{diff}** more to unlock **Free Doorstep Delivery** (Current"
      f" total: ₹{total_bill})"
  )

# ====================================================
# RESIDENT DETAILS & ADDRESS FORM
# ====================================================
with st.expander("📍 Delivery / Pickup & Contact Details", expanded=True):
  col_u1, col_u2, col_u3 = st.columns([1, 1, 1])
  flat_no = col_u1.text_input(
      "Tower & Flat / Door No.*", placeholder="e.g. Tower 2, Flat 603"
  )
  resident_name = col_u2.text_input("Your Name*", placeholder="Name")
  phone = col_u3.text_input("Mobile No.*", placeholder="9876543210")

  col_d1, col_d2 = st.columns([1, 1])
  with col_d1:
    if total_bill >= MIN_DELIVERY_AMOUNT:
      delivery_choice = st.radio(
          "Service Mode*",
          ["🛵 Doorstep Delivery (Free)", "🏢 Clubhouse Counter Pickup"],
          horizontal=True,
      )
    else:
      delivery_choice = "🏢 Clubhouse Counter Pickup"
      st.caption(
          "Service Mode: **Clubhouse Counter Pickup** *(Min ₹150 for doorstep"
          " delivery)*"
      )

  with col_d2:
    slot = st.selectbox("Preferred Time Slot*", slots)

# ====================================================
# CHECKOUT & TRANSACTIONAL SUBMIT
# ====================================================
st.markdown("### 🛒 Order Summary")
col_pay1, col_pay2 = st.columns([1, 1])

with col_pay1:
  if order_items:
    summary_table = pd.DataFrame(order_items)[
        ["item_name", "quantity", "unit_price", "subtotal"]
    ]
    summary_table.columns = ["Item", "Qty", "Price (₹)", "Total (₹)"]
    st.dataframe(summary_table, hide_index=True, use_container_width=True)
    st.markdown(f"## Total Bill: **₹{total_bill}**")
  else:
    st.write("Add dishes from the menu above to calculate your bill.")

with col_pay2:
  if total_bill > 0 and flat_no and resident_name and phone:
    order_id = f"ORD-{datetime.now().strftime('%H%M%S')}"
    upi_url, qr_bytes = create_upi_intent(
        UPI_ID, BRAND_NAME, total_bill, order_id
    )

    st.markdown("#### Instant UPI Payment")
    st.link_button(
        f"👉 Tap to Pay ₹{total_bill} via UPI App",
        upi_url,
        type="primary",
        use_container_width=True,
    )

    with st.expander("Show UPI QR Code"):
      st.image(qr_bytes, width=170)
      st.caption(f"UPI ID: `{UPI_ID}` | Ref Note: `Order_{order_id}`")

    utr_input = st.text_input(
        "UPI Reference ID / UTR (Optional)",
        placeholder="Enter 12-digit UTR after payment",
    )

    if st.button(
        "✅ Confirm & Submit Order", type="primary", use_container_width=True
    ):
      # SQL Statements for Atomic Transaction
      insert_order_query = text("""
                INSERT INTO orders (order_id, pickup_date, order_type, delivery_type, slot, flat_no, name, phone, total_inr, utr_ref, status)
                VALUES (:order_id, :pickup_date, :order_type, :delivery_type, :slot, :flat_no, :name, :phone, :total_inr, :utr_ref, :status)
            """)

      insert_item_query = text("""
                INSERT INTO order_items (order_id, item_id, item_name, quantity, unit_price, subtotal)
                VALUES (:order_id, :item_id, :item_name, :quantity, :unit_price, :subtotal)
            """)

      clean_delivery_type = (
          "Doorstep Delivery"
          if "Doorstep" in delivery_choice
          else "Counter Pickup"
      )

      order_params = {
          "order_id": order_id,
          "pickup_date": selected_date,
          "order_type": "Now" if "Today" in str(order_type) else "Pre-Order",
          "delivery_type": clean_delivery_type,
          "slot": slot,
          "flat_no": flat_no,
          "name": resident_name,
          "phone": phone,
          "total_inr": total_bill,
          "utr_ref": utr_input if utr_input else "N/A",
          "status": "Confirmed",
      }

      # Atomic Transaction Execution
      try:
        with engine.begin() as db_conn:
          # 1. Insert Order Header
          db_conn.execute(insert_order_query, order_params)

          # 2. Insert Line Items referencing the order_id
          for item in order_items:
            item_record = {
                "order_id": order_id,
                "item_id": item["item_id"],
                "item_name": item["item_name"],
                "quantity": item["quantity"],
                "unit_price": item["unit_price"],
                "subtotal": item["subtotal"],
            }
            db_conn.execute(insert_item_query, item_record)

        if "Doorstep" in clean_delivery_type:
          st.success(
              f"🎉 Order #{order_id} placed! It will be delivered to"
              f" {flat_no} around {slot}."
          )
        else:
          st.success(
              f"🎉 Order #{order_id} placed! Please collect at the clubhouse"
              f" counter at {slot}."
          )
        st.balloons()
      except Exception as ex:
        st.error(f"Database write error: {ex}")
  elif total_bill > 0:
    st.warning(
        "⚠️ Please fill in Tower/Flat No, Name, and Mobile Number to place your"
        " order."
    )
# At the bottom/main section of views/order.py:
def render():
    # Place all your resident order layout, forms, and buttons here
    ...
