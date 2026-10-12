"""Screen C: Staffing Requirements & Rule Configuration.
"""

import streamlit as st
import pandas as pd
from datetime import time, date, timedelta
from src.state import init_session_state
from src.configuration import WEEKDAY_NAMES, INT_TO_WEEKDAY, WEEKDAY_TO_INT
from src.feasibility import run_feasibility_precheck

init_session_state()

st.title("⚙️ Staffing Requirements & Rule Engine")
st.markdown(
    "Configure per-shift minimum headcount by weekday, create day-range rules, "
    "set date overrides, and observe instant mathematical feasibility analysis."
)

config = st.session_state.config
employees = st.session_state.employees
start_date = st.session_state.start_date
end_date = st.session_state.end_date

# Recalculate immediate feasibility
feas_report = run_feasibility_precheck(config, employees, start_date, end_date)
st.session_state.feasibility_report = feas_report

# Immediate Feasibility Banner
if feas_report.is_feasible:
    st.success(f"🟢 **FEASIBILITY PRECHECK: {feas_report.status.value}** - {feas_report.messages[0] if feas_report.messages else 'Mathematical capacity is sufficient.'}")
else:
    st.error(f"🔴 **FEASIBILITY PRECHECK: {feas_report.status.value}** - Immediate contradiction detected!")
    for msg in feas_report.messages:
        st.warning(f"⚠️ {msg}")
    for sug in feas_report.suggestions:
        st.info(f"💡 Recommended Fix: {sug}")

st.markdown("---")

tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Weekday Base Staffing Matrix",
    "📅 Day-Range Rule Editor",
    "📌 Date-Specific Overrides",
    "⏱️ Shift Definitions & Constraints",
])

with tab1:
    st.subheader("Base Minimum Staffing Matrix (7 Days × 3 Shifts)")
    st.caption("Default minimum staffing for each weekday. Values deliberately reflect 24/7 operational demand.")

    matrix_rows = []
    for wd_idx, wd_name in enumerate(WEEKDAY_NAMES):
        matrix_rows.append({
            "Day": wd_name,
            "S1 Minimum": config.base_matrix[wd_idx]["S1"],
            "S2 Minimum": config.base_matrix[wd_idx]["S2"],
            "S3 Minimum": config.base_matrix[wd_idx]["S3"],
            "Total Minimum": (
                config.base_matrix[wd_idx]["S1"]
                + config.base_matrix[wd_idx]["S2"]
                + config.base_matrix[wd_idx]["S3"]
            ),
        })
    df_matrix = pd.DataFrame(matrix_rows)

    edited_df = st.data_editor(
        df_matrix,
        column_config={
            "Day": st.column_config.TextColumn(disabled=True),
            "S1 Minimum": st.column_config.NumberColumn(min_value=0, max_value=50, step=1),
            "S2 Minimum": st.column_config.NumberColumn(min_value=0, max_value=50, step=1),
            "S3 Minimum": st.column_config.NumberColumn(min_value=0, max_value=50, step=1),
            "Total Minimum": st.column_config.NumberColumn(disabled=True),
        },
        use_container_width=True,
        hide_index=True,
    )

    if st.button("Save Matrix Changes", type="primary"):
        for _, row in edited_df.iterrows():
            wd_i = WEEKDAY_TO_INT[row["Day"]]
            config.base_matrix[wd_i]["S1"] = int(row["S1 Minimum"])
            config.base_matrix[wd_i]["S2"] = int(row["S2 Minimum"])
            config.base_matrix[wd_i]["S3"] = int(row["S3 Minimum"])
        st.success("Base matrix updated successfully!")
        st.rerun()

with tab2:
    st.subheader("Day-Range Rule Editor")
    st.markdown(
        "Apply staffing rules across custom weekday ranges (e.g., Wednesday through Saturday peak). "
        "Day-range rules take precedence over the base matrix."
    )

    with st.expander("➕ Create New Day-Range Rule", expanded=False):
        rule_name = st.text_input("Rule Name:", value="Peak Midweek Rule")
        c1, c2 = st.columns(2)
        with c1:
            start_wd = st.selectbox("Start Weekday:", WEEKDAY_NAMES, index=2)  # Wednesday
        with c2:
            end_wd = st.selectbox("End Weekday:", WEEKDAY_NAMES, index=5)    # Saturday

        st.write("**Shift Minimums to Apply:**")
        cs1, cs2, cs3 = st.columns(3)
        with cs1:
            r_s1 = st.number_input("S1 Minimum", min_value=0, max_value=50, value=6)
        with cs2:
            r_s2 = st.number_input("S2 Minimum", min_value=0, max_value=50, value=14)
        with cs3:
            r_s3 = st.number_input("S3 Minimum", min_value=0, max_value=50, value=16)

        if st.button("Add Day-Range Rule"):
            s_idx = WEEKDAY_TO_INT[start_wd]
            e_idx = WEEKDAY_TO_INT[end_wd]
            config.add_day_range_rule(
                name=rule_name,
                start_weekday=s_idx,
                end_weekday=e_idx,
                shift_mins={"S1": int(r_s1), "S2": int(r_s2), "S3": int(r_s3)},
            )
            st.success(f"Added rule '{rule_name}' successfully!")
            st.rerun()

    st.write("#### Active Day-Range Rules")
    if config.day_range_rules:
        for rule in config.day_range_rules:
            c_r1, c_r2, c_r3 = st.columns([3, 4, 1])
            with c_r1:
                st.write(f"**{rule.name}** ({INT_TO_WEEKDAY[rule.start_weekday]} to {INT_TO_WEEKDAY[rule.end_weekday]})")
            with c_r2:
                st.write(f"S1={rule.shift_mins.get('S1', '-')}, S2={rule.shift_mins.get('S2', '-')}, S3={rule.shift_mins.get('S3', '-')}")
            with c_r3:
                if st.button("Delete", key=f"del_{rule.rule_id}"):
                    config.remove_day_range_rule(rule.rule_id)
                    st.rerun()
    else:
        st.info("No custom day-range rules defined. Using base matrix.")

with tab3:
    st.subheader("Date-Specific Staffing Overrides")
    st.markdown("Override shift minimums for specific calendar dates (Highest Precedence).")

    with st.form("date_override_form"):
        target_d = st.date_input("Target Date:", value=start_date)
        c1, c2, c3 = st.columns(3)
        with c1:
            o_s1 = st.number_input("S1 Minimum", min_value=0, max_value=50, value=5)
        with c2:
            o_s2 = st.number_input("S2 Minimum", min_value=0, max_value=50, value=10)
        with c3:
            o_s3 = st.number_input("S3 Minimum", min_value=0, max_value=50, value=10)
        reason = st.text_input("Reason / Note:", value="Product Release Window")

        if st.form_submit_button("Add Date Override"):
            config.set_date_override(
                target_date=target_d,
                shift_mins={"S1": int(o_s1), "S2": int(o_s2), "S3": int(o_s3)},
                reason=reason,
            )
            st.success(f"Added override for {target_d}!")
            st.rerun()

    if config.date_overrides:
        st.write("#### Configured Date Overrides")
        for dt, ov in list(config.date_overrides.items()):
            co1, co2, co3 = st.columns([2, 4, 1])
            with co1:
                st.write(f"**{dt}** ({INT_TO_WEEKDAY[dt.weekday()]})")
            with co2:
                st.write(f"S1={ov.shift_mins.get('S1')}, S2={ov.shift_mins.get('S2')}, S3={ov.shift_mins.get('S3')} | {ov.reason}")
            with co3:
                if st.button("Remove", key=f"del_ov_{dt}"):
                    config.remove_date_override(dt)
                    st.rerun()

with tab4:
    st.subheader("Shift Definitions & Core Health Parameters")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### Shift Operating Hours")
        for sc in ["S1", "S2", "S3"]:
            s_def = config.shifts[sc]
            st.write(f"**{sc} ({s_def.name})**: {s_def.start_time.strftime('%H:%M')} to {s_def.end_time.strftime('%H:%M')} {'(Next Day)' if s_def.crosses_midnight else ''} | Duration: {s_def.duration_hours:.1f} hrs")

    with c2:
        st.markdown("#### Health & Work-Cycle Rules")
        st.write(f"- **Standard Cycle:** {config.consecutive_work_days} consecutive workdays + {config.consecutive_off_days} consecutive OFF days")
        st.write(f"- **Minimum Elapsed Rest:** {config.min_rest_hours} hours")
        st.write(f"- **Monthly S3 Hard Cap:** {config.monthly_s3_cap} shifts / employee / calendar month")
        st.write(f"- **Max Night Blocks / Month:** {config.max_night_blocks_per_month} five-night blocks")
        st.write(f"- **Post-Night OFF Days:** Mandatory {config.consecutive_off_days} consecutive OFF days")
