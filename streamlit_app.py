import io
import urllib.parse
from datetime import date, datetime, timedelta
import pandas as pd
import qrcode
from sqlalchemy import create_engine, text
import streamlit as st

# ====================================================
# BRANDING & CONFIGURATION
# ====================================================
BRAND_NAME = "TASTY India"
BRAND_TAGLINE = "Tasty South grp"
UPI_ID = "yourfriend@upi"  # Update with real UPI VPA
ADMIN_PIN = "5678"

st.set_page_config(
    page_title=f"{BRAND_NAME} - Clubhouse Canteen",
    page_icon="🍛",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS Styling matching the Brand Palette
st.markdown(
    """
    <style>
        :root {
            --brand-red: #8B1E1E;
            --brand-yellow: #EAA224;
            --bg-soft: #FFF9F2;
        }
        .main {
            background-color: #FAFAFA;
        }
        .brand-header {
            text-align: center;
            padding: 10px 0 20px 0;
        }
        .brand-title {
            color: var(--brand-yellow);
            font-size: 2.3rem;
            font-weight: 800;
            letter-spacing: 1px;
            margin-bottom: 0px;
            text-transform: uppercase;
        }
        .brand-title span {
            color: var(--brand-red);
        }
        .brand-subtitle {
            color: var(--brand-yellow);
            font-weight: 600;
            font-size: 1.05rem;
            margin-top: -5px;
            letter-spacing: 0.5px;
        }
        .menu-card {
            background-color: white;
            border-radius: 12px;
            padding: 16px 20px;
            margin-bottom: 12px;
            border-left: 5px solid var(--brand-red);
            box-shadow: 0 2px 8px rgba(0,0,0,0.06);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .menu-card-title {
            font-size: 1.1rem;
            font-weight: 700;
            color: #222;
            margin: 0;
        }
        .menu-card-price {
            font-size: 1.1rem;
            font-weight: 700;
            color: var(--brand-red);
        }
        .stButton>button {
            border-radius: 8px;
            font-weight: 600;
        }
        div[data-testid="stMetricValue"] {
            color: var(--brand-red);
            font-weight: 700;
        }
    </style>
""",
    unsafe_allow_html=True,
)


# --- Database Connection ---
@st.cache_resource
def get_engine():
  db_url = st.secrets["postgres"]["url"]
  return create_engine(db_url, pool_pre_ping=True)


engine = get_engine()


# Database Queries
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
# SIDEBAR NAVIGATION
# ====================================================
with st.sidebar:
  try:
    st.image("logo.png", use_container_width=True)
  except Exception:
    st.markdown("### 🍛 TASTY India")

  st.caption("Clubhouse Canteen Ordering System")
  st.divider()

  view_mode = st.radio(
      "Navigate",
      ["🍽️ Order Food", "🔐 Kitchen & Admin Portal"],
      index=0,
  )

  st.divider()
  st.info("⏱️ **Pre-Order Cutoff:** 10:00 PM for next-day breakfast/lunch.")

# ====================================================
# VIEW 1: RESIDENT ORDERING PORTAL
# ====================================================
if view_mode == "🍽️ Order Food":
  st.markdown(
      """
        <div class="brand-header">
            <h1 class="brand-title">TASTY <span>India</span></h1>
            <p class="brand-subtitle">Tasty South grp</p>
        </div>
    """,
      unsafe_allow_html=True,
  )

  # Timeline & Schedule Selector
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
        f"📅 **Pickup Date:** `{selected_date.strftime('%A, %d %B %Y')}`"
    )

  st.markdown("---")

  # Resident Delivery Information
  with st.expander("📍 Resident Pickup & Contact Details", expanded=True):
    col_u1, col_u2, col_u3 = st.columns([1, 1, 1])
    flat_no = col_u1.text_input("Flat / Door No.*", placeholder="e.g. B-603")
    resident_name = col_u2.text_input("Your Name*", placeholder="Balaji M")
    phone = col_u3.text_input("Mobile No.*", placeholder="9876543210")
    slot = st.selectbox("Select Pickup Slot*", slots)

  # Menu Section
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
            max_cap = (
                int(row["daily_cap"]) if pd.notna(row["daily_cap"]) else 50
            )
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
  else:
    st.info("No active menu items available at the moment.")

  # Checkout Bar
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
      st.write("Add dishes from the menu above to see your bill.")

  with col_pay2:
    if total_bill > 0 and flat_no and resident_name and phone:
      order_id = f"ORD-{datetime.now().strftime('%H%M%S')}"
      upi_url, qr_bytes = create_upi_intent(
          UPI_ID, BRAND_NAME, total_bill, order_id
      )

      st.markdown("#### Instant UPI Payment")
      st.link_button(
          f"👉 Tap to Pay ₹{total_bill} via UPI",
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
        insert_order_query = text("""
                    INSERT INTO orders (order_id, pickup_date, order_type, slot, flat_no, name, phone, total_inr, utr_ref, status)
                    VALUES (:order_id, :pickup_date, :order_type, :slot, :flat_no, :name, :phone, :total_inr, :utr_ref, :status)
                """)
        insert_item_query = text("""
                    INSERT INTO order_items (order_id, item_id, item_name, quantity, unit_price, subtotal)
                    VALUES (:order_id, :item_id, :item_name, :quantity, :unit_price, :subtotal)
                """)

        order_params = {
            "order_id": order_id,
            "pickup_date": selected_date,
            "order_type": "Now" if "Today" in str(order_type) else "Pre-Order",
            "slot": slot,
            "flat_no": flat_no,
            "name": resident_name,
            "phone": phone,
            "total_inr": total_bill,
            "utr_ref": utr_input if utr_input else "N/A",
            "status": "Confirmed",
        }

        try:
          with engine.begin() as db_conn:
            db_conn.execute(insert_order_query, order_params)
            for item in order_items:
              item["order_id"] = order_id
              db_conn.execute(insert_item_query, item)
          st.success(
              f"🎉 Order #{order_id} placed successfully! Collect at {slot}."
          )
          st.balloons()
        except Exception as ex:
          st.error(f"Error recording order: {ex}")
    elif total_bill > 0:
      st.warning("⚠️ Please fill in Flat No, Name, and Mobile Number to pay.")

# ====================================================
# VIEW 2: KITCHEN & ADMIN DASHBOARD
# ====================================================
else:
  st.markdown(
      f"## 🔐 {BRAND_NAME} — Admin & Kitchen Portal", unsafe_allow_html=True
  )
  admin_pin = st.text_input("Enter Admin PIN", type="password")

  if admin_pin == ADMIN_PIN:
    admin_tab1, admin_tab2 = st.tabs(
        ["👨‍🍳 Kitchen Prep & Live Queue", "✏️ Menu & Pricing Manager"]
    )

    # SUB-VIEW A: KITCHEN PREP & QUEUE
    with admin_tab1:
      filter_date = st.date_input(
          "Filter Orders By Date",
          value=date.today() + timedelta(days=1),
          help="Choose pickup date to view batch prep requirements",
      )

      # Metrics Row
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
          "Total Dishes Ordered",
          daily_orders["items_ordered"].count()
          if not daily_orders.empty
          else 0,
      )

      st.markdown("---")

      # Aggregated Batch Quantities
      st.subheader(f"🥣 Batch Cooking Requirements for {filter_date}")
      summary_df = load_kitchen_summary(filter_date)

      if not summary_df.empty:
        st.dataframe(summary_df, hide_index=True, use_container_width=True)
      else:
        st.info(f"No orders registered for {filter_date} yet.")

      # Full Ticket Queue
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

    # SUB-VIEW B: MENU & PRICING MANAGER
    with admin_tab2:
      st.subheader("✏️ Live Menu & Stock Controller")
      st.caption(
          "Changes made here reflect immediately on the resident ordering"
          " screen."
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
                  "Active?", default=True
              ),
          },
      )

      if st.button("💾 Save Menu Changes", type="primary"):
        try:
          with engine.begin() as db_conn:
            db_conn.execute(
                text("TRUNCATE TABLE menu RESTART IDENTITY CASCADE;")
            )
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
