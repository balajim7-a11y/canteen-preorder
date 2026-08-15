import streamlit as st

st.set_page_config(
    page_title="Tasty India - Clubhouse Canteen",
    page_icon="🍛",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Set up clean URL routes
order_page = st.Page(
    "views/order.py",
    title="Place Order",
    icon="🍽️",
    url_path="order",
    default=True,
)
admin_page = st.Page(
    "views/admin.py", title="Kitchen & Admin", icon="🔐", url_path="admin"
)

# Navigation
pg = st.navigation(
    {"Tasty India": [order_page], "Kitchen Management": [admin_page]}
)

pg.run()
