"""Screen B: Employee Management & Excel Import.
"""

import streamlit as st
import pandas as pd
import os
import openpyxl
from datetime import datetime, date
from src.state import init_session_state
from src.models import Employee
from src.excel_handler import load_employees_from_excel, create_sample_employees_workbook

init_session_state()

st.title("👥 Employee Pool Management")
st.markdown("Manage employee records, upload customized Excel workbooks, map columns, and toggle active status.")

employees = st.session_state.employees

# Metrics
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Total Pool", f"{len(employees)} Staff")
with col2:
    active_count = sum(1 for e in employees if e.active)
    st.metric("Active Staff", f"{active_count} Staff")
with col3:
    inactive_count = len(employees) - active_count
    st.metric("Inactive Staff", f"{inactive_count} Staff")

st.markdown("---")

tab1, tab2, tab3 = st.tabs(["📋 Current Employee Pool", "📤 Excel Import & Mapping", "➕ Add / Edit Employee"])

with tab1:
    st.subheader("Current Employee Roster Pool")
    # Convert to DataFrame for easy display
    emp_rows = []
    for e in employees:
        emp_rows.append({
            "Employee_ID": e.id,
            "Employee_Name": e.name,
            "Active": e.active,
            "Approved_Leave_Days": len(e.approved_leave),
            "Initial_Phase": e.initial_phase if e.initial_phase is not None else "Auto",
            "Role": e.extra_attributes.get("Role", "General"),
        })
    df_emps = pd.DataFrame(emp_rows)
    st.dataframe(df_emps, use_container_width=True, height=400)

    # Download Sample Workbook
    sample_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "sample_employees.xlsx")
    if os.path.exists(sample_path):
        with open(sample_path, "rb") as f:
            st.download_button(
                label="📥 Download Standard 50-Employee Template (Excel)",
                data=f.read(),
                file_name="sample_50_employees.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

with tab2:
    st.subheader("Import Employee Excel Workbook")
    uploaded_file = st.file_uploader(
        "Upload Employee Workbook (.xlsx)",
        type=["xlsx"],
        help="Upload an Excel file containing employee IDs, names, active flags, and optional approved leave.",
    )

    if uploaded_file is not None:
        try:
            wb = openpyxl.load_workbook(uploaded_file, read_only=True)
            sheet_names = wb.sheetnames
            selected_sheet = st.selectbox("Select Worksheet:", sheet_names)

            # Preview columns
            wb_preview = openpyxl.load_workbook(uploaded_file, data_only=True)
            ws_preview = wb_preview[selected_sheet]
            first_row = [str(cell.value).strip() for cell in ws_preview[1] if cell.value is not None]

            st.write("**Columns Detected in Worksheet:**", first_row)

            # Column mapping
            st.markdown("#### Column Mapping")
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                id_col = st.selectbox("Employee ID Column:", first_row, index=first_row.index("Employee_ID") if "Employee_ID" in first_row else 0)
            with c2:
                name_col = st.selectbox("Employee Name Column:", first_row, index=first_row.index("Employee_Name") if "Employee_Name" in first_row else min(1, len(first_row)-1))
            with c3:
                active_col = st.selectbox("Active Column (Optional):", ["None"] + first_row, index=first_row.index("Active") + 1 if "Active" in first_row else 0)
            with c4:
                leave_col = st.selectbox("Leave Column (Optional):", ["None"] + first_row, index=first_row.index("Approved_Leave") + 1 if "Approved_Leave" in first_row else 0)

            col_map = {
                "id": id_col,
                "name": name_col,
            }
            if active_col != "None":
                col_map["active"] = active_col
            if leave_col != "None":
                col_map["leave"] = leave_col

            if st.button("Apply & Import Employees", type="primary"):
                uploaded_file.seek(0)
                loaded_emps, msgs = load_employees_from_excel(
                    uploaded_file, sheet_name=selected_sheet, col_mapping=col_map
                )
                if loaded_emps:
                    st.session_state.employees = loaded_emps
                    st.session_state.current_schedule = None  # Reset schedule
                    st.success(f"Successfully loaded {len(loaded_emps)} employees from Excel!")
                    for m in msgs:
                        st.info(m)
                    st.rerun()
                else:
                    st.error("Failed to load employees. See errors below:")
                    for m in msgs:
                        st.error(m)
        except Exception as ex:
            st.error(f"Error parsing uploaded Excel: {ex}")

with tab3:
    st.subheader("Manual Employee Entry / Status Update")
    with st.form("add_employee_form"):
        new_id = st.text_input("Employee ID (e.g. EMP051):")
        new_name = st.text_input("Employee Name:")
        is_active = st.checkbox("Active for Scheduling", value=True)
        role = st.text_input("Role / Skill:", value="Support Engineer")
        submitted = st.form_submit_button("Add Employee")

        if submitted:
            if not new_id.strip() or not new_name.strip():
                st.error("Employee ID and Name cannot be empty.")
            elif any(e.id == new_id.strip() for e in st.session_state.employees):
                st.error(f"Employee ID '{new_id}' already exists in the pool.")
            else:
                new_emp = Employee(
                    id=new_id.strip(),
                    name=new_name.strip(),
                    active=is_active,
                    extra_attributes={"Role": role},
                )
                st.session_state.employees.append(new_emp)
                st.session_state.current_schedule = None
                st.success(f"Added employee {new_id} ({new_name}) successfully!")
                st.rerun()
