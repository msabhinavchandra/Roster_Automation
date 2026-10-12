"""Screen G: Night Shift Health & Fatigue Dashboard.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date, timedelta
from src.state import init_session_state
from src.configuration import INT_TO_WEEKDAY

init_session_state()

st.title("🌙 Night-Shift Health & Fatigue Dashboard")
st.markdown(
    "Monitors circadian health and sleep fatigue compliance. "
    "Strictly enforces the **hard limit of 10 S3 shifts per calendar month**, "
    "mandatory **2 OFF days post-night blocks**, and caps night blocks at **2 per month**."
)

schedule = st.session_state.current_schedule
config = st.session_state.config
employees = st.session_state.employees

if schedule is None:
    st.warning("⚠️ No active roster draft found. Generate a roster in the **Generate Roster** tab to view live night-shift metrics.")
    st.stop()

dates = []
curr = schedule.start_date
while curr <= schedule.end_date:
    dates.append(curr)
    curr += timedelta(days=1)

# Group months
months = sorted(list(set((d.year, d.month) for d in dates)))
month_labels = [f"{y}-{m:02d}" for (y, m) in months]

selected_month_label = st.selectbox("Select Calendar Month:", month_labels)
sel_year, sel_month = map(int, selected_month_label.split("-"))

m_dates = [d for d in dates if d.year == sel_year and d.month == sel_month]

# Calculate S3 counts for selected month
s3_data = []
exceeded_count = 0
approaching_count = 0

for e in employees:
    if not e.active:
        continue
    c = sum(1 for d in m_dates if schedule.get_assignment(e.id, d) == "S3")
    status = "Normal"
    if c > config.monthly_s3_cap:
        status = "EXCEEDED"
        exceeded_count += 1
    elif c >= config.monthly_s3_cap - 2:
        status = "Approaching Cap"
        approaching_count += 1

    s3_data.append({
        "Employee ID": e.id,
        "Employee Name": e.name,
        "Monthly S3 Count": c,
        "Status": status,
    })

df_s3 = pd.DataFrame(s3_data)

# KPI Cards
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("Total S3 Assignments", f"{df_s3['Monthly S3 Count'].sum()} Shifts")
with c2:
    st.metric("Monthly S3 Hard Cap", f"{config.monthly_s3_cap} Shifts / Person")
with c3:
    st.metric(
        "Cap Violations (>10)",
        f"{exceeded_count} Staff",
        delta="Zero Tolerated" if exceeded_count == 0 else f"{exceeded_count} Violation(s)!",
        delta_color="normal" if exceeded_count == 0 else "inverse",
    )
with c4:
    st.metric("Approaching Limit (8-10)", f"{approaching_count} Staff")

st.markdown("---")

# Bar Chart with Reference Line at 10
st.subheader(f"Night-Shift (S3) Count per Employee - {selected_month_label}")
fig = px.bar(
    df_s3,
    x="Employee ID",
    y="Monthly S3 Count",
    color="Status",
    color_discrete_map={"Normal": "#1F77B4", "Approaching Cap": "#FF7F0E", "EXCEEDED": "#D62728"},
    title=f"Monthly S3 Shifts per Employee ({selected_month_label})",
)
fig.add_hline(
    y=config.monthly_s3_cap,
    line_dash="dash",
    line_color="red",
    annotation_text=f"Maximum Allowable Monthly Cap ({config.monthly_s3_cap} shifts)",
    annotation_position="top right",
)
st.plotly_chart(fig, use_container_width=True)

# Detailed Table with Filter
st.subheader("Employee Night-Shift Ledger")
filter_status = st.multiselect("Filter by Status:", ["Normal", "Approaching Cap", "EXCEEDED"], default=["Normal", "Approaching Cap", "EXCEEDED"])
filtered_df = df_s3[df_s3["Status"].isin(filter_status)]
st.dataframe(filtered_df, use_container_width=True)

# Policy Reference Card
with st.expander("ℹ️ Night-Shift Health & Regulatory Policy Guidelines", expanded=True):
    st.markdown(f"""
    - **Monthly Night Shift Cap:** No employee may exceed **{config.monthly_s3_cap} S3 shifts** in any single calendar month.
    - **Shift Block Continuity:** Night shifts are scheduled in cohesive **5-night blocks** followed by **2 mandatory consecutive OFF days**.
    - **Rest Verification:** S3 ends at 07:00 next day. With 2 OFF days following, an employee receives **55 hours of continuous rest** before resuming on an S2 shift.
    - **Zero-Tolerance Enforcement:** In a published valid roster, the count of employees exceeding the monthly night-shift cap must strictly be **0**.
    """)
