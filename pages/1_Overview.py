"""Screen A: System Overview Dashboard.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date, timedelta
from src.state import init_session_state
from src.feasibility import run_feasibility_precheck
from src.configuration import INT_TO_WEEKDAY

init_session_state()

st.title("📊 System Overview & Live Dashboard")

config = st.session_state.config
employees = st.session_state.employees
start_date = st.session_state.start_date
end_date = st.session_state.end_date
schedule = st.session_state.current_schedule

feas_report = run_feasibility_precheck(config, employees, start_date, end_date)
st.session_state.feasibility_report = feas_report

# Top Metric Cards
col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.metric("Active Employees", f"{sum(1 for e in employees if e.active)} / {len(employees)}")
with col2:
    st.metric("Scheduling Mode", config.mode.value)
with col3:
    st.metric("Feasibility Precheck", feas_report.status.value)
with col4:
    if schedule and schedule.validation_report:
        st.metric("Validation Status", schedule.validation_report.status.value)
    else:
        st.metric("Validation Status", "No Draft")
with col5:
    pub_status = "PUBLISHED" if (schedule and schedule.is_published) else ("DRAFT READY" if schedule else "NOT GENERATED")
    st.metric("Roster State", pub_status)

st.markdown("---")

# Precheck Details & Capacity
st.subheader("Capacity & Feasibility Precheck Snapshot")
if feas_report.is_feasible:
    st.success(f"✅ **{feas_report.status.value}**: {feas_report.messages[0] if feas_report.messages else 'All mathematical bounds satisfied.'}")
else:
    st.error(f"❌ **{feas_report.status.value}**: Mathematical conflict detected before solver run!")
    for msg in feas_report.messages:
        st.warning(f"⚠️ {msg}")
    for sug in feas_report.suggestions:
        st.info(f"💡 Suggestion: {sug}")

st.markdown("---")

# If schedule exists, show detailed charts
if schedule:
    st.subheader("Live Coverage & Allocation Metrics")
    dates = []
    curr = schedule.start_date
    while curr <= schedule.end_date:
        dates.append(curr)
        curr += timedelta(days=1)

    eff_matrix = config.get_effective_matrix_for_range(schedule.start_date, schedule.end_date)
    chart_data = []
    for d in dates:
        req, _ = eff_matrix[d]
        a_s1 = sum(1 for e in employees if schedule.get_assignment(e.id, d) == "S1")
        a_s2 = sum(1 for e in employees if schedule.get_assignment(e.id, d) == "S2")
        a_s3 = sum(1 for e in employees if schedule.get_assignment(e.id, d) == "S3")

        chart_data.append({"Date": d.strftime("%Y-%m-%d"), "Shift": "S1 (Morning)", "Required": req.get("S1", 0), "Assigned": a_s1})
        chart_data.append({"Date": d.strftime("%Y-%m-%d"), "Shift": "S2 (Evening)", "Required": req.get("S2", 0), "Assigned": a_s2})
        chart_data.append({"Date": d.strftime("%Y-%m-%d"), "Shift": "S3 (Night)", "Required": req.get("S3", 0), "Assigned": a_s3})

    df_chart = pd.DataFrame(chart_data)
    fig = px.bar(
        df_chart,
        x="Date",
        y="Assigned",
        color="Shift",
        barmode="group",
        title="Assigned vs Required Staffing by Shift",
        color_discrete_map={"S1 (Morning)": "#4B8BBE", "S2 (Evening)": "#FFD43B", "S3 (Night)": "#D9534F"}
    )
    st.plotly_chart(fig, use_container_width=True)

    # Night Shift Utilization Overview
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Night-Shift (S3) Utilization Distribution")
        s3_counts = [sum(1 for d in dates if schedule.get_assignment(e.id, d) == "S3") for e in employees if e.active]
        df_s3 = pd.DataFrame({"Monthly S3 Shifts": s3_counts})
        fig_s3 = px.histogram(df_s3, x="Monthly S3 Shifts", nbins=11, title="Distribution of Night Shifts per Employee")
        fig_s3.add_vline(x=config.monthly_s3_cap, line_dash="dash", line_color="red", annotation_text=f"Monthly Cap ({config.monthly_s3_cap})")
        st.plotly_chart(fig_s3, use_container_width=True)

    with c2:
        st.subheader("Roster Summary Statistics")
        tot_s1 = sum(1 for e in employees for d in dates if schedule.get_assignment(e.id, d) == "S1")
        tot_s2 = sum(1 for e in employees for d in dates if schedule.get_assignment(e.id, d) == "S2")
        tot_s3 = sum(1 for e in employees for d in dates if schedule.get_assignment(e.id, d) == "S3")
        tot_off = sum(1 for e in employees for d in dates if schedule.get_assignment(e.id, d) == "OFF")
        tot_work = tot_s1 + tot_s2 + tot_s3

        st.write(f"- **Total Working Shifts Assigned:** {tot_work}")
        st.write(f"- **Total S1 Shifts:** {tot_s1} ({tot_s1/tot_work*100:.1f}%)")
        st.write(f"- **Total S2 Shifts:** {tot_s2} ({tot_s2/tot_work*100:.1f}%)")
        st.write(f"- **Total S3 Shifts:** {tot_s3} ({tot_s3/tot_work*100:.1f}%)")
        st.write(f"- **Total OFF Days:** {tot_off}")
        st.write(f"- **Average Work Days / Employee:** {tot_work / len(employees):.1f} days")
else:
    st.info("ℹ️ No roster generated yet. Go to **Generate Roster** tab to create a draft schedule.")
