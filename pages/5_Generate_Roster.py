"""Screen E: Generate Roster Engine.
"""

import streamlit as st
import time
from datetime import date, timedelta
from src.state import init_session_state
from src.models import SchedulingMode, ValidationStatus, FeasibilityStatus
from src.feasibility import run_feasibility_precheck
from src.scheduler import RosterScheduler

init_session_state()

st.title("🚀 Roster Generation Engine")
st.markdown("Configure operational parameters, review mathematical prechecks, and launch the OR-Tools CP-SAT scheduling engine.")

config = st.session_state.config
employees = st.session_state.employees

col1, col2 = st.columns([1, 1])
with col1:
    st.subheader("Scheduling Parameters")
    c_d1, c_d2 = st.columns(2)
    with c_d1:
        start_d = st.date_input("Start Date:", value=st.session_state.start_date)
    with c_d2:
        end_d = st.date_input("End Date:", value=st.session_state.end_date)

    if start_d != st.session_state.start_date or end_d != st.session_state.end_date:
        st.session_state.start_date = start_d
        st.session_state.end_date = end_d

    mode_options = [
        "MODE_B (Health-First, Coverage-Oriented - Recommended)",
        "MODE_A (Strict Preferred Rotation: S1->S2->S3->S2->S1)",
        "MODE_C (Fairness-Optimized Rotation)",
    ]
    curr_mode_idx = 0
    if config.mode == SchedulingMode.MODE_A:
        curr_mode_idx = 1
    elif config.mode == SchedulingMode.MODE_C:
        curr_mode_idx = 2

    selected_mode_str = st.radio("Scheduling Mode:", mode_options, index=curr_mode_idx)
    if "MODE_B" in selected_mode_str:
        config.mode = SchedulingMode.MODE_B
    elif "MODE_A" in selected_mode_str:
        config.mode = SchedulingMode.MODE_A
    elif "MODE_C" in selected_mode_str:
        config.mode = SchedulingMode.MODE_C

    time_limit = st.slider("Solver Time Limit (seconds):", min_value=5, max_value=120, value=config.solver_time_limit_seconds, step=5)
    config.solver_time_limit_seconds = time_limit

with col2:
    st.subheader("Mathematical Feasibility Precheck")
    feas_report = run_feasibility_precheck(config, employees, start_d, end_d)
    st.session_state.feasibility_report = feas_report

    if feas_report.is_feasible:
        st.success(f"🟢 **{feas_report.status.value}**")
        st.write("All aggregate capacity, 5/2 work cycles, and monthly S3 caps passed mathematical necessary conditions.")
        st.write(f"- Total Demand: **{feas_report.capacity_metrics.get('total_required_assignments')}** shifts")
        st.write(f"- Total Capacity: **{feas_report.capacity_metrics.get('effective_total_capacity')}** employee-days")
        st.write(f"- Average Weekly S3 Demand: **{feas_report.capacity_metrics.get('average_weekly_s3_required')}** shifts")
    else:
        st.error(f"🔴 **{feas_report.status.value}**")
        for m in feas_report.messages:
            st.warning(f"⚠️ {m}")
        for s in feas_report.suggestions:
            st.info(f"💡 Suggestion: {s}")

st.markdown("---")

generate_btn = st.button("🚀 Generate Roster Now", type="primary", use_container_width=True)

if generate_btn:
    if feas_report.status == FeasibilityStatus.INFEASIBLE:
        st.error("Cannot launch solver: Feasibility precheck identified proven mathematical contradictions. Please resolve the reported shortages first.")
    else:
        with st.spinner(f"Running OR-Tools CP-SAT solver for {config.mode.value} (up to {time_limit}s)..."):
            scheduler = RosterScheduler(config)
            schedule, val_report, msg = scheduler.generate(
                employees=employees,
                start_date=start_d,
                end_date=end_d,
                mode=config.mode,
                time_limit_seconds=time_limit,
            )

            if schedule is not None and val_report.is_valid:
                st.session_state.current_schedule = schedule
                st.session_state.last_status_message = msg
                st.success(f"🎉 {msg}")
                st.balloons()
                st.info("Navigate to **Review and Publish** to inspect the full schedule and download the official Excel workbook.")
            elif schedule is not None:
                st.session_state.current_schedule = schedule
                st.warning(f"Draft generated but has validation warnings/issues: {msg}")
            else:
                st.error(f"❌ Failed to generate valid roster: {msg}")
                if config.mode == SchedulingMode.MODE_A:
                    st.info("💡 **Mode A Diagnostic**: Rigid S1->S2->S3->S2->S1 rotation forces equal shift frequencies, which conflicts with asymmetric demand (S3=86, S1=34). Click below to generate with Mode B.")
                    if st.button("Switch to Mode B & Generate"):
                        config.mode = SchedulingMode.MODE_B
                        st.rerun()

# Current schedule status indicator
if st.session_state.current_schedule:
    s = st.session_state.current_schedule
    st.markdown("---")
    st.subheader("Current Active Draft")
    st.write(f"- **Roster Period:** {s.start_date} to {s.end_date} ({(s.end_date - s.start_date).days + 1} days)")
    st.write(f"- **Generated Under Mode:** {s.mode.value}")
    st.write(f"- **Solver Status:** {s.solver_status} (Solved in {s.solve_time_seconds:.2f}s)")
    if s.validation_report:
        st.write(f"- **Validation Status:** {s.validation_report.status.value} ({s.validation_report.error_count} errors, {s.validation_report.warning_count} warnings)")
