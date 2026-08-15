import streamlit as st

st.set_page_config(
    page_title="Tasty India - Clubhouse Canteen",
    page_icon="🍛",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Read URL query parameter: ?view=admin or ?view=order
view = st.query_params.get("view", "order").lower()

if view == "admin":
    import views.admin as admin_view
    admin_view.render()
else:
    import views.order as order_view
    order_view.render()
