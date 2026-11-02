import streamlit as st

import database as db
import reminders

st.set_page_config(page_title="SAGE · AI Study Planner", page_icon="🎓", layout="wide",
                   initial_sidebar_state="expanded")


@st.cache_resource
def boot():
    db.init_db()
    return reminders.start_scheduler()


boot()

for key, value in {"last_provider": "—", "sync_status": "—", "chat": [], "pomo": None}.items():
    st.session_state.setdefault(key, value)

# Open the plan if one exists, otherwise start on the configuration page
has_plan = db.active_subject() is not None and bool(db.get_sessions(statuses=["planned"]))
pages = [
    st.Page("views/schedule.py", title="Today's Plan", icon="🗓️", url_path="plan", default=has_plan),
    st.Page("views/configuration.py", title="Study Plan Configuration", icon="⚙️",
            url_path="setup", default=not has_plan),
]
# position="hidden": SAGE draws its own navigation inside the sidebar
st.navigation(pages, position="hidden").run()