import io
import urllib.parse
from datetime import date, datetime, timedelta
import pandas as pd
import qrcode
import streamlit as st
from streamlit_gsheets import GSheetsConnection

# ====================================================
# 1. CONFIGURATION (Update with your friend's details)
# ====================================================
UPI_ID = "yourfriend@upi"  # e.g., 9876543210@paytm, user@okaxis
PAYEE_NAME = "Clubhouse Canteen"  # Business / Account holder name
ADMIN_PIN = "5678"  # PIN for kitchen dashboard access

st.set_page_config(
    page_title="Clubhouse Canteen Pre-Order", page_icon="🍲", layout="centered"
)

# Connect to Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)


# Helper: Load Menu
def load_menu():
  return conn.read(worksheet="menu", ttl="1m")


# Helper: Load Orders
def load_orders():
  return conn.read(worksheet="orders", ttl=0)


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
    ["🛒 Place Pre-Order", "👨‍🍳 Kitchen Dashboard"]
)

# ====================================================
# TAB 1: RESIDENTS PRE-ORDER
# ====================================================
with tab_order:
  tomorrow = date.today() + timedelta(days=1)
  st.header(f"Menu for Tomorrow ({tomorrow.strftime('%d %b, %Y')})")

  with st.expander("Resident & Delivery Details", expanded=True):
    c1, c2 = st.columns(2)
    flat_no = c1.text_input("Flat / Door Number (e.g. A-402)*")
    resident_name = c2.text_input("Your Name*")
    phone = c1.text_input("Mobile Number*")
    slot = c2.selectbox(
        "Pickup Time Slot*",
        [
            "Breakfast: 7:30 AM - 8:15 AM",
            "Breakfast: 8:15 AM - 9:00 AM",
            "Lunch: 12:30 PM - 1:30 PM",
            "Lunch: 1:30 PM - 2:15 PM",
            "Dinner: 7:30 PM - 8:30 PM",
        ],
    )

  st.subheader("Select Items")
  try:
    menu_df = load_menu()
    active_items = menu_df[menu_df["active"] == True]
  except Exception as e:
    st.error("Unable to load menu. Please check Google Sheet connection.")
    active_items = pd.DataFrame()

  order_items = {}
  total_bill = 0

  if not active_items.empty:
    for _, row in active_items.iterrows():
      c_name, c_price, c_qty = st.columns([3, 1, 2])
      c_name.write(f"**{row['item_name']}** ({row['category']})")
      c_price.write(f"₹{row['price']}")
      qty = c_qty.number_input(
          "Qty",
          min_value=0,
          max_value=int(row["daily_cap"]),
          value=0,
          key=f"item_{row['id']}",
      )
      if qty > 0:
        order_items[row["item_name"]] = qty
        total_bill += qty * row["price"]

  st.divider()
  st.markdown(f"### Total Amount: **₹{total_bill}**")

  if total_bill > 0 and flat_no and resident_name and phone:
    order_id = f"ORD-{datetime.now().strftime('%H%M%S')}"
    upi_url, qr_bytes = create_upi_intent(
        UPI_ID, PAYEE_NAME, total_bill, order_id
    )

    st.subheader("Payment")

    # Mobile direct click-to-pay button
    st.link_button(
        f"👉 Tap to Pay ₹{total_bill} directly via UPI App",
        upi_url,
        type="primary",
        use_container_width=True,
    )

    # QR Code option for residents on desktop / secondary phone
    with st.expander("Or scan QR Code to pay", expanded=False):
      st.image(qr_bytes, width=180)
      st.caption(f"UPI ID: `{UPI_ID}` | Ref Note: `Order_{order_id}`")

    # Optional UTR / Reference confirmation
    utr_input = st.text_input(
        "UPI Reference ID / UTR (Optional, from your payment app)"
    )

    if st.button(
        "Confirm & Submit Order", type="primary", use_container_width=True
    ):
      items_str = ", ".join([f"{k} x{v}" for k, v in order_items.items()])
      new_record = pd.DataFrame([{
          "order_id": order_id,
          "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
          "pickup_date": str(tomorrow),
          "slot": slot,
          "flat_no": flat_no,
          "name": resident_name,
          "phone": phone,
          "items": items_str,
          "total_inr": total_bill,
          "utr_ref": utr_input if utr_input else "N/A",
          "status": "Confirmed",
      }])

      try:
        existing_orders = load_orders()
        updated_orders = pd.concat(
            [existing_orders, new_record], ignore_index=True
        )
        conn.update(worksheet="orders", data=updated_orders)
        st.success(f"Order #{order_id} placed! Please collect it at {slot}.")
        st.balloons()
      except Exception as ex:
        st.error(f"Error recording order: {ex}")
  elif total_bill > 0:
    st.info("Please fill in Flat Number, Name, and Phone above to proceed.")

# ====================================================
# TAB 2: KITCHEN DASHBOARD
# ====================================================
with tab_kitchen:
  st.header("Kitchen Production View")
  admin_pin = st.text_input("Enter Kitchen PIN", type="password")

  if admin_pin == ADMIN_PIN:
    try:
      orders_df = load_orders()
      if orders_df.empty or "items" not in orders_df.columns:
        st.info("No orders recorded yet.")
      else:
        tomorrow_str = str(date.today() + timedelta(days=1))
        active_orders = orders_df[orders_df["pickup_date"] == tomorrow_str]

        st.subheader(f"Summary for {tomorrow_str}")

        item_counts = {}
        for entry in active_orders["items"].dropna():
          for item in str(entry).split(", "):
            if " x" in item:
              name, count = item.rsplit(" x", 1)
              item_counts[name] = item_counts.get(name, 0) + int(count)

        if item_counts:
          summary_df = pd.DataFrame(
              list(item_counts.items()), columns=["Item", "Quantity to Cook"]
          )
          st.dataframe(summary_df, use_container_width=True)

        st.subheader("Individual Order Queue")
        st.dataframe(active_orders, use_container_width=True)
    except Exception as e:
      st.error(f"Error reading orders sheet: {e}")
  elif admin_pin:
    st.error("Incorrect PIN")
