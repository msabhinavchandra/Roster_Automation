"""Roster Automation System - Streamlit Entry Point & Home Hub.
"""

import streamlit as st
from datetime import date
from src.state import init_session_state
from src.feasibility import run_feasibility_precheck

st.set_page_config(
    page_title="Roster Automation System",
    page_icon="📅",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_session_state()

# Sidebar summary
st.sidebar.title("📅 Roster Automation")
st.sidebar.caption("24/7 Production & Release Support Roster Engine")

config = st.session_state.config
employees = st.session_state.employees
start_date = st.session_state.start_date
end_date = st.session_state.end_date
schedule = st.session_state.current_schedule

# Update feasibility report
feas_report = run_feasibility_precheck(config, employees, start_date, end_date)
st.session_state.feasibility_report = feas_report

st.sidebar.markdown("---")
st.sidebar.subheader("System Status")
st.sidebar.info(f"**Mode:** {config.mode.value}")
st.sidebar.info(f"**Period:** {start_date} to {end_date}")
st.sidebar.info(f"**Active Staff:** {sum(1 for e in employees if e.active)} / {len(employees)}")

if feas_report.is_feasible:
    st.sidebar.success(f"Feasibility: {feas_report.status.value}")
else:
    st.sidebar.error(f"Feasibility: {feas_report.status.value}")

if schedule:
    if schedule.is_published:
        st.sidebar.success("Roster: PUBLISHED")
    elif schedule.validation_report and schedule.validation_report.is_valid:
        st.sidebar.success("Roster: VALID DRAFT")
    else:
        st.sidebar.warning("Roster: DRAFT (Pending Validation)")
else:
    st.sidebar.warning("Roster: No Draft Generated")

# Main Content
st.title("Enterprise Roster Automation System")
st.markdown(
    "Automated, mathematically optimal 24/7 production and release support rostering "
    "powered by **Google OR-Tools CP-SAT**. Strictly enforces employee health, consecutive work/rest cycles, "
    "and monthly night-shift caps without external AI dependencies."
)

st.markdown("---")

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Total Pool", f"{len(employees)} Employees", f"{sum(1 for e in employees if e.active)} Active")
with col2:
    total_days = (end_date - start_date).days + 1
    st.metric("Roster Duration", f"{total_days} Days", f"{start_date.strftime('%b %d')} - {end_date.strftime('%b %d')}")
with col3:
    weekly_s3 = feas_report.capacity_metrics.get("average_weekly_s3_required", 0)
    st.metric("Weekly S3 Demand", f"{weekly_s3} Shifts", f"Monthly Cap: {config.monthly_s3_cap} max")
with col4:
    if feas_report.is_feasible:
        st.metric("Precheck Feasibility", "FEASIBLE", delta="Math bounds valid", delta_color="normal")
    else:
        st.metric("Precheck Feasibility", "INFEASIBLE", delta="Conflict detected", delta_color="inverse")

st.markdown("---")
st.subheader("Operational Workflow")

c1, c2 = st.columns(2)
with c1:
    st.markdown("""
    ### 1. 👥 [Employees](pages/2_Employees.py)
    - Review loaded pool (50 default employees).
    - Upload custom Excel employee workbooks.
    - Inspect active statuses and approved leave.

    ### 2. ⚙️ [Staffing Rules](pages/3_Staffing_Rules.py)
    - Edit the 7-day × 3-shift minimum staffing matrix.
    - Configure custom weekday-range rules (e.g. Wednesday to Saturday peak).
    - Review immediate mathematical feasibility alerts.

    ### 3. 🏖️ [Holidays & Leave](pages/4_Holidays_and_Leave.py)
    - Configure public holidays and operational policies (Sunday vs Normal vs Custom).
    - Manage individual employee leave dates.
    """)

with c2:
    st.markdown("""
    ### 4. 🚀 [Generate Roster](pages/5_Generate_Roster.py)
    - Choose mode: **Mode B (Health-First Default)**, **Mode A (Strict Rotation)**, or **Mode C (Fairness)**.
    - Set date range, solver timeouts, and run CP-SAT.

    ### 5. 📋 [Review & Publish](pages/6_Review_and_Publish.py)
    - Inspect interactive color-coded schedule grid.
    - Perform manual shift overrides with instant revalidation.
    - Download publication-grade multi-tab Excel workbook.

    ### 6. 🌙 [Night Shifts & Analytics](pages/7_Night_Shift_Dashboard.py)
    - Monitor employee night-shift loads against the 10-shift monthly cap.
    - Historical continuity analysis and compliance scoring.
    """)
