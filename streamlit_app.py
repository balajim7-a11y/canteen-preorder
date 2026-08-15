import streamlit as st

st.set_page_config(
    page_title="Tasty India - Clubhouse Canteen",
    page_icon="🍛",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Read ?view=admin or ?view=order from the browser URL
current_view = st.query_params.get("view", "order").lower()

if current_view == "admin":
  from views import admin

  admin.render()
else:
  from views import order

  order.render()
