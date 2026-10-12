"""Screen F: Review, Edit, Validate, and Publish Roster.
"""

import streamlit as st
import pandas as pd
from datetime import date, timedelta
from src.state import init_session_state
from src.validation import validate_roster
from src.excel_handler import export_roster_to_excel
from src.configuration import INT_TO_WEEKDAY

init_session_state()

st.title("📋 Review, Edit & Publish Roster")
st.markdown("Inspect generated schedules, perform manual adjustments with instant revalidation, approve publication, and download the official Excel workbook.")

schedule = st.session_state.current_schedule
config = st.session_state.config
employees = st.session_state.employees

if schedule is None:
    st.warning("⚠️ No roster draft is currently loaded. Please go to **Generate Roster** tab to create a draft schedule.")
    st.stop()

dates = []
curr = schedule.start_date
while curr <= schedule.end_date:
    dates.append(curr)
    curr += timedelta(days=1)

# Action Bar
col_a1, col_a2, col_a3, col_a4 = st.columns(4)

with col_a1:
    if st.button("🔄 Validate Draft", use_container_width=True):
        val_report = validate_roster(schedule, config, employees)
        schedule.validation_report = val_report
        if val_report.is_valid:
            st.success(f"Validation Passed: {val_report.status.value}")
        else:
            st.error(f"Validation Failed: {val_report.status.value} ({val_report.error_count} errors)")
        st.rerun()

with col_a2:
    if st.button("💾 Save Draft", use_container_width=True):
        st.success("Draft saved successfully to session state.")

with col_a3:
    is_valid_draft = schedule.validation_report and schedule.validation_report.is_valid
    publish_btn = st.button(
        "✅ Approve & Publish",
        type="primary",
        disabled=not is_valid_draft,
        use_container_width=True,
        help="Publication requires zero validation errors." if not is_valid_draft else "Officially publish this approved roster.",
    )
    if publish_btn:
        schedule.is_published = True
        # Save to disk
        output_stream = export_roster_to_excel(
            schedule=schedule,
            config=config,
            employees=employees,
            feasibility_report=st.session_state.feasibility_report,
            output_path=config.output_filename,
        )
        st.success(f"🎉 Roster published and saved to '{config.output_filename}'!")
        st.balloons()
        st.rerun()

with col_a4:
    excel_stream = export_roster_to_excel(
        schedule=schedule,
        config=config,
        employees=employees,
        feasibility_report=st.session_state.feasibility_report,
    )
    st.download_button(
        label="📥 Download Excel Workbook",
        data=excel_stream.getvalue(),
        file_name="roster_published.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

st.markdown("---")

# Publication Banner
if schedule.is_published:
    st.success("🏆 **OFFICIALLY PUBLISHED**: This roster has passed all hard validation checks and is locked for operational deployment.")
elif is_valid_draft:
    st.info("🟢 **VALID DRAFT**: All hard constraints satisfied. Ready for approval.")
else:
    st.error("🔴 **INVALID DRAFT**: Violations detected. Fix conflicts or re-generate.")

# Tabs for Views and Manual Edit
tab_grid, tab_edit, tab_coverage, tab_validation = st.tabs([
    "📅 Full Roster Grid",
    "✏️ Manual Shift Override",
    "📊 Daily Shift Coverage",
    "⚠️ Centralized Validation Report",
])

with tab_grid:
    st.subheader("Interactive Roster Grid")
    roster_rows = []
    for e in employees:
        row = {"Employee ID": e.id, "Employee Name": e.name}
        for d in dates:
            row[d.strftime("%Y-%m-%d (%a)")] = schedule.get_assignment(e.id, d)
        roster_rows.append(row)
    df_roster = pd.DataFrame(roster_rows)

    st.dataframe(df_roster, use_container_width=True, height=500)

with tab_edit:
    st.subheader("Manual Shift Adjustment")
    st.markdown("Perform manual shift adjustments. Any change triggers full centralized revalidation.")

    c1, c2, c3 = st.columns(3)
    with c1:
        edit_emp_id = st.selectbox("Select Employee:", [e.id for e in employees if e.active])
    with c2:
        edit_date = st.selectbox("Select Date:", dates, format_func=lambda d: f"{d.strftime('%Y-%m-%d (%a)')}")
    with c3:
        curr_val = schedule.get_assignment(edit_emp_id, edit_date)
        shift_choices = ["S1", "S2", "S3", "OFF"]
        new_shift = st.selectbox("Assign New Shift:", shift_choices, index=shift_choices.index(curr_val))

    if st.button("Apply Shift Change"):
        schedule.set_assignment(edit_emp_id, edit_date, new_shift)
        schedule.is_published = False  # Reset publication
        # Re-run authoritative validation
        val_report = validate_roster(schedule, config, employees)
        schedule.validation_report = val_report

        if val_report.is_valid:
            st.success(f"Shift updated to {new_shift}. Centralized validation PASSED!")
        else:
            st.error(f"Shift updated, but introduced {val_report.error_count} validation error(s)!")
        st.rerun()

with tab_coverage:
    st.subheader("Daily Coverage & Deficit Analysis")
    eff_matrix = config.get_effective_matrix_for_range(schedule.start_date, schedule.end_date)
    cov_rows = []
    for d in dates:
        req, src = eff_matrix[d]
        a_s1 = sum(1 for e in employees if schedule.get_assignment(e.id, d) == "S1")
        a_s2 = sum(1 for e in employees if schedule.get_assignment(e.id, d) == "S2")
        a_s3 = sum(1 for e in employees if schedule.get_assignment(e.id, d) == "S3")
        r_s1 = req.get("S1", 0)
        r_s2 = req.get("S2", 0)
        r_s3 = req.get("S3", 0)

        cov_rows.append({
            "Date": d.strftime("%Y-%m-%d"),
            "Weekday": INT_TO_WEEKDAY[d.weekday()],
            "S1 Req": r_s1,
            "S1 Assigned": a_s1,
            "S1 Delta": a_s1 - r_s1,
            "S2 Req": r_s2,
            "S2 Assigned": a_s2,
            "S2 Delta": a_s2 - r_s2,
            "S3 Req": r_s3,
            "S3 Assigned": a_s3,
            "S3 Delta": a_s3 - r_s3,
            "Total Req": r_s1 + r_s2 + r_s3,
            "Total Assigned": a_s1 + a_s2 + a_s3,
            "Rule Source": src,
        })
    st.dataframe(pd.DataFrame(cov_rows), use_container_width=True)

with tab_validation:
    st.subheader("Validation Issues & Rules Checklist")
    val_report = schedule.validation_report
    if val_report:
        if val_report.issues:
            v_rows = []
            for issue in val_report.issues:
                v_rows.append({
                    "Severity": issue.severity,
                    "Rule": issue.rule_name,
                    "Employee": issue.employee_id or "All",
                    "Date": issue.date.strftime("%Y-%m-%d") if issue.date else "Overall",
                    "Message": issue.message,
                })
            st.dataframe(pd.DataFrame(v_rows), use_container_width=True)
        else:
            st.success("✅ Zero validation issues! All operational and health constraints are 100% satisfied.")
    else:
        st.info("Validation report not available. Click 'Validate Draft' above.")
