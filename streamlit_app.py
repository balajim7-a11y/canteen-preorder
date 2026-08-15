import streamlit as st

# Global page configuration
st.set_page_config(
    page_title="Tasty India - Clubhouse Canteen",
    page_icon="🍛",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Define the isolated view pages and their respective URLs
order_page = st.Page(
    "views/order.py",
    title="Place Order",
    icon="🍽️",
    url_path="order",
    default=True,
)

admin_page = st.Page(
    "views/admin.py",
    title="Kitchen & Admin",
    icon="🔐",
    url_path="admin",
)

# Register pages inside the navigation menu
pg = st.navigation(
    {
        "Tasty India": [order_page],
        "Kitchen Management": [admin_page],
    }
)

# Run current routed page
pg.run()
