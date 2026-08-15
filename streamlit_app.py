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
ADMIN_PIN = "5678"
MIN_DELIVERY_AMOUNT = 150

st.set_page_config(
    page_title=f"{BRAND_NAME} - Clubhouse Canteen",
    page_icon="🍛",
    layout="wide",
    initial_sidebar_state="collapsed",
)

if "is_admin_mode" not in st.session_state:
  st.session_state.is_admin_mode = False


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


@st.cache_data(ttl=60)
def load_menu():
  with engine.connect() as conn:
    result = conn.execute(
        text(
            "SELECT id, category, item_name, price, daily_cap, active FROM menu"
            " ORDER BY id ASC"
        )
    )
    rows = result.fetchall()
    return (
        pd.DataFrame(rows, columns=result.keys()) if rows else pd.DataFrame()
    )


@st.cache_data(ttl=5)
def load_orders(target_date):
  query = text("""
        SELECT 
            o.order_id,
            COALESCE(o.delivery_type, 'Counter Pickup') AS delivery_type,
            o.slot,
            o.flat_no,
            o.name,
            o.phone,
            o.total_inr,
            o.status,
            COALESCE(STRING_AGG(oi.item_name || ' (x' || oi.quantity || ')', ', '), 'No items') AS items_ordered,
            o.utr_ref
        FROM orders o
        LEFT JOIN order_items oi ON o.order_id = oi.order_id
        WHERE CAST(o.pickup_date AS DATE) = CAST(:target_date AS DATE)
        GROUP BY o.order_id, o.delivery_type, o.created_at, o.pickup_date, o.order_type, o.slot, o.flat_no, o.name, o.phone, o.total_inr, o.utr_ref, o.status
        ORDER BY o.created_at DESC;
    """)
  with engine.connect() as conn:
    result = conn.execute(query, {"target_date": str(target_date)})
    rows = result.fetchall()
    if rows:
      return pd.DataFrame(rows, columns=result.keys())
    return pd.DataFrame(
        columns=[
            "order_id",
            "delivery_type",
            "slot",
            "flat_no",
            "name",
            "phone",
            "total_inr",
            "status",
            "items_ordered",
            "utr_ref",
        ]
    )


@st.cache_data(ttl=5)
def load_kitchen_summary(target_date):
  query = text("""
        SELECT 
            oi.item_name AS "Menu Item",
            SUM(oi.quantity) AS "Batch Quantity"
        FROM order_items oi
        JOIN orders o ON oi.order_id = o.order_id
        WHERE CAST(o.pickup_date AS DATE) = CAST(:target_date AS DATE)
        GROUP BY oi.item_name
        ORDER BY "Batch Quantity" DESC;
    """)
  with engine.connect() as conn:
    result = conn.execute(query, {"target_date": str(target_date)})
    rows = result.fetchall()
    if rows:
      return pd.DataFrame(rows, columns=result.keys())
    return pd.DataFrame(columns=["Menu Item", "Batch Quantity"])


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
# SIDEBAR / VIEW SWITCHER
# ====================================================
with st.sidebar:
  try:
    st.image("logo.png", width=140)
  except Exception:
    st.markdown("### 🍛 TASTY India")

  st.write("---")
  if st.session_state.is_admin_mode:
    if st.button("⬅️ Switch to Resident Ordering View"):
      st.session_state.is_admin_mode = False
      st.rerun()
  else:
    if st.button("🔐 Staff / Kitchen Login"):
      st.session_state.is_admin_mode = True
      st.rerun()

# ====================================================
# VIEW 1: KITCHEN & ADMIN DASHBOARD
# ====================================================
if st.session_state.is_admin_mode:
  col_title, col_btn = st.columns([4, 1])
  with col_title:
    st.title(f"🔐 {BRAND_NAME} — Admin & Kitchen Portal")
  with col_btn:
    if st.button("Back to Order Page"):
      st.session_state.is_admin_mode = False
      st.rerun()

  admin_pin = st.text_input("Enter Admin PIN to Unlock", type="password")

  if admin_pin == ADMIN_PIN:
    admin_tab1, admin_tab2 = st.tabs(
        ["👨‍🍳 Kitchen Prep & Live Queue", "✏️ Menu Manager"]
    )

    with admin_tab1:
      col_f1, col_f2 = st.columns([1, 1])
      with col_f1:
        filter_date = st.date_input(
            "📅 Filter Orders By Date",
            value=date.today(),
        )
      with col_f2:
        slot_filter = st.selectbox(
            "⏰ Filter by Time Slot",
            [
                "All Slots",
                "Breakfast",
                "Lunch",
                "Snacks",
                "Dinner",
                "Immediate / ASAP",
            ],
        )

      daily_orders = load_orders(filter_date)

      if not daily_orders.empty and slot_filter != "All Slots":
        daily_orders = daily_orders[
            daily_orders["slot"].str.contains(
                slot_filter, case=False, na=False
            )
        ]

      # Metrics summary
      m1, m2, m3 = st.columns(3)
      m1.metric(
          "Total Orders", len(daily_orders) if not daily_orders.empty else 0
      )
      m2.metric(
          "Total Revenue",
          f"₹{int(daily_orders['total_inr'].sum()) if not daily_orders.empty else 0}",
      )
      delivery_count = (
          len(
              daily_orders[
                  daily_orders["delivery_type"] == "Doorstep Delivery"
              ]
          )
          if not daily_orders.empty
          else 0
      )
      m3.metric("Doorstep Deliveries 🛵", delivery_count)

      st.divider()

      # Section 1: Kitchen Batch Summary
      with st.expander(
          "🥣 **Batch Cooking Requirements (Total Counts)**", expanded=False
      ):
        summary_df = load_kitchen_summary(filter_date)
        if not summary_df.empty:
          st.dataframe(summary_df, hide_index=True, use_container_width=True)
        else:
          st.info("No items scheduled for cooking on this date.")

      st.markdown("### 📋 Order Details & Ticket Inspector")

      if not daily_orders.empty:
        # Create user-friendly label for dropdown selector
        order_options = {}
        for _, o_row in daily_orders.iterrows():
          badge = (
              "🛵 Doorstep"
              if "Doorstep" in str(o_row["delivery_type"])
              else "🏢 Pickup"
          )
          label = (
              f"#{o_row['order_id']} | Flat: {o_row['flat_no']} |"
              f" {o_row['slot']} | {badge} | ₹{o_row['total_inr']}"
          )
          order_options[label] = o_row["order_id"]

        selected_label = st.selectbox(
            "👉 Select an Order to View Details:", list(order_options.keys())
        )
        selected_order_id = order_options[selected_label]

        # Fetch selected order data
        selected_order = daily_orders[
            daily_orders["order_id"] == selected_order_id
        ].iloc[0]
        is_delivery = "Doorstep" in str(selected_order["delivery_type"])

        # Top Information Banner
        st.markdown(
            f"""
            <div style="background-color: {'#FFF3E0' if is_delivery else '#E3F2FD'}; 
                        padding: 16px; border-radius: 8px; margin: 12px 0; border: 1px solid {'#FFE0B2' if is_delivery else '#BBDEFB'};">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <span style="font-size: 1.4rem; font-weight: 800; color: #111;">Order #{selected_order['order_id']}</span>
                    <span style="background: {'#D32F2F' if is_delivery else '#1565C0'}; color: #FFFFFF; font-weight: 700; padding: 4px 12px; border-radius: 20px; font-size: 0.9rem;">
                        {'🛵 DOORSTEP DELIVERY' if is_delivery else '🏢 COUNTER PICKUP'}
                    </span>
                </div>
                <div style="font-size: 1.05rem; color: #333; line-height: 1.6;">
                    📍 <b>Flat / Door No:</b> <span style="font-size: 1.25rem; font-weight: 800; color: #D32F2F;">{selected_order['flat_no']}</span><br>
                    ⏰ <b>Preferred Slot:</b> <span style="font-weight: 700;">{selected_order['slot']}</span><br>
                    👤 <b>Resident:</b> {selected_order['name']} &nbsp;|&nbsp; 📞 <a href="tel:{selected_order['phone']}"><b>{selected_order['phone']}</b></a><br>
                    💳 <b>Payment UTR / Ref:</b> <code>{selected_order['utr_ref']}</code>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Line-by-line item breakdown from order_items table
        st.markdown("#### 🍴 Ordered Items Breakdown")
        items_query = text("""
            SELECT 
                item_name AS "Dish / Item",
                quantity AS "Qty",
                unit_price AS "Price (₹)",
                subtotal AS "Subtotal (₹)"
            FROM order_items
            WHERE order_id = :order_id
            ORDER BY id ASC;
        """)

        with engine.connect() as conn:
          items_res = conn.execute(
              items_query, {"order_id": selected_order_id}
          )
          items_rows = items_res.fetchall()
          items_df = (
              pd.DataFrame(items_rows, columns=items_res.keys())
              if items_rows
              else pd.DataFrame()
          )

        if not items_df.empty:
          st.dataframe(items_df, hide_index=True, use_container_width=True)
          col_tot1, col_tot2 = st.columns([2, 1])
          with col_tot2:
            st.markdown(
                f"<h3 style='text-align: right; color: #2E7D32;'>Total Bill:"
                f" ₹{selected_order['total_inr']}</h3>",
                unsafe_allow_html=True,
            )
        else:
          items_list = str(selected_order["items_ordered"]).split(", ")
          for dish in items_list:
            st.markdown(f"- 🍽️ **{dish.strip()}**")
          st.markdown(f"**Total Bill:** ₹{selected_order['total_inr']}")

        # Status Update Control
        st.markdown("#### ⚡ Update Ticket Status")
        col_s1, col_s2 = st.columns([2, 1])
        with col_s1:
          status_options = [
              "Confirmed",
              "Preparing",
              "Ready for Pickup / Out for Delivery",
              "Delivered",
          ]
          current_status = (
              selected_order["status"]
              if selected_order["status"] in status_options
              else "Confirmed"
          )
          new_status = st.selectbox(
              "Current Status",
              status_options,
              index=status_options.index(current_status),
              key=f"status_select_{selected_order_id}",
          )

        with col_s2:
          st.write("")
          st.write("")
          if st.button("💾 Update Status", type="primary"):
            update_sql = text("""
                UPDATE orders 
                SET status = :new_status 
                WHERE order_id = :order_id;
            """)
            try:
              with engine.begin() as db_conn:
                db_conn.execute(
                    update_sql,
                    {
                        "new_status": new_status,
                        "order_id": selected_order_id,
                    },
                )
              st.cache_data.clear()
              st.success(
                  f"Order #{selected_order_id} marked as '{new_status}'!"
              )
              st.rerun()
            except Exception as e:
              st.error(f"Failed to update status: {e}")

        st.divider()

        # All Orders Quick Table (Compact Overview)
        with st.expander("📄 View All Order Headers for this Date"):
          st.dataframe(
              daily_orders[[
                  "order_id",
                  "delivery_type",
                  "slot",
                  "flat_no",
                  "name",
                  "phone",
                  "total_inr",
                  "status",
              ]],
              hide_index=True,
              use_container_width=True,
          )

      else:
        st.info(
            f"No orders registered for {filter_date} under the selected slot"
            " filter."
        )

    with admin_tab2:
      st.subheader("Manage Menu & Pricing")
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
                  "Price (₹)", min_value=1
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
          st.cache_data.clear()
          st.success("Menu updated successfully!")
          st.rerun()
        except Exception as e:
          st.error(f"Error saving menu: {e}")
  elif admin_pin:
    st.error("Incorrect PIN")

# ====================================================
# VIEW 2: RESIDENT ORDERING PORTAL
# ====================================================
else:
  col_logo, col_head = st.columns([1, 4])
  with col_logo:
    try:
      st.image("logo.png", width=100)
    except Exception:
      st.write("🍛")
  with col_head:
    st.title(BRAND_NAME)
    st.caption(f"✨ *{BRAND_TAGLINE}* | Clubhouse Cafeteria")

  col_t1, col_t2 = st.columns(2)
  with col_t1:
    order_type = st.radio(
        "Order Timeline",
        ["Today (Instant)", "Tomorrow (Pre-Order)"],
        horizontal=True,
    )

  if order_type == "Today (Instant)":
    selected_date = date.today()
    slots = [
        "ASAP (15-20 mins)",
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
    st.markdown(f"📅 **Date:** `{selected_date.strftime('%A, %d %B %Y')}`")

  st.subheader("📋 Select Dishes")
  try:
    menu_df = load_menu()
    active_items = (
        menu_df[menu_df["active"] == True]
        if not menu_df.empty
        else pd.DataFrame()
    )
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
                "Qty",
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

  if total_bill >= MIN_DELIVERY_AMOUNT:
    st.success("🛵 **Eligible for FREE Doorstep Delivery!**")
  elif total_bill > 0:
    st.info(
        f"💡 Add **₹{MIN_DELIVERY_AMOUNT - total_bill}** more for Free Doorstep"
        " Delivery"
    )

  with st.expander("📍 Delivery / Pickup & Contact Details", expanded=True):
    col_u1, col_u2, col_u3 = st.columns(3)
    flat_no = col_u1.text_input("Tower & Flat No.*", placeholder="e.g. T2-603")
    resident_name = col_u2.text_input("Name*", placeholder="Your Name")
    phone = col_u3.text_input("Mobile No.*", placeholder="9876543210")

    col_d1, col_d2 = st.columns(2)
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
            "Service Mode: **Clubhouse Counter Pickup** *(Min ₹150 for"
            " delivery)*"
        )
    with col_d2:
      slot = st.selectbox("Preferred Slot*", slots)

  st.markdown("### 🛒 Order Summary")
  col_pay1, col_pay2 = st.columns(2)
  with col_pay1:
    if order_items:
      summary_table = pd.DataFrame(order_items)[
          ["item_name", "quantity", "unit_price", "subtotal"]
      ]
      summary_table.columns = ["Item", "Qty", "Price (₹)", "Total (₹)"]
      st.dataframe(summary_table, hide_index=True, use_container_width=True)
      st.markdown(f"## Total Bill: **₹{total_bill}**")
    else:
      st.write("Add dishes to see your bill.")

  with col_pay2:
    if total_bill > 0 and flat_no and resident_name and phone:
      order_id = f"ORD-{datetime.now().strftime('%H%M%S')}"
      upi_url, qr_bytes = create_upi_intent(
          UPI_ID, BRAND_NAME, total_bill, order_id
      )

      st.link_button(
          f"👉 Tap to Pay ₹{total_bill} via UPI",
          upi_url,
          type="primary",
          use_container_width=True,
      )
      with st.expander("Show UPI QR Code"):
        st.image(qr_bytes, width=170)
        st.caption(f"UPI: `{UPI_ID}` | Ref Note: `Order_{order_id}`")

      utr_input = st.text_input("UPI Reference / UTR (Optional)")

      if st.button(
          "✅ Confirm & Submit Order", type="primary", use_container_width=True
      ):
        insert_order_query = text("""
            INSERT INTO orders (order_id, pickup_date, order_type, delivery_type, slot, flat_no, name, phone, total_inr, utr_ref, status)
            VALUES (:order_id, :pickup_date, :order_type, :delivery_type, :slot, :flat_no, :name, :phone, :total_inr, :utr_ref, :status)
        """)
        insert_item_query = text("""
            INSERT INTO order_items (order_id, item_id, item_name, quantity, unit_price, subtotal)
            VALUES (:order_id, :item_id, :item_name, :quantity, :unit_price, :subtotal)
        """)

        clean_delivery = (
            "Doorstep Delivery"
            if "Doorstep" in delivery_choice
            else "Counter Pickup"
        )
        order_params = {
            "order_id": order_id,
            "pickup_date": selected_date,
            "order_type": "Now" if "Today" in str(order_type) else "Pre-Order",
            "delivery_type": clean_delivery,
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
              item_record = {
                  "order_id": order_id,
                  "item_id": item["item_id"],
                  "item_name": item["item_name"],
                  "quantity": item["quantity"],
                  "unit_price": item["unit_price"],
                  "subtotal": item["subtotal"],
              }
              db_conn.execute(insert_item_query, item_record)
          st.cache_data.clear()
          st.success(f"🎉 Order #{order_id} placed successfully!")
          st.balloons()
        except Exception as ex:
          st.error(f"Error saving order: {ex}")
    elif total_bill > 0:
      st.warning("⚠️ Please fill in Flat No, Name, and Mobile Number.")

  # Discrete staff entry button
  st.write("---")
  col_foot, col_staff = st.columns([4, 1])
  with col_staff:
    if st.button("🔐 Staff Login"):
      st.session_state.is_admin_mode = True
      st.rerun()
