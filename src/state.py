"""Session State Management Helper for Streamlit Application.
Provides uniform initialization and state persistence across all multi-page tabs.
"""

from __future__ import annotations
import os
from datetime import date
from typing import List, Optional
import streamlit as st

from src.models import Employee, RosterSchedule, FeasibilityReport, SchedulingMode
from src.configuration import RosterConfig
from src.excel_handler import load_employees_from_excel
from src.feasibility import run_feasibility_precheck


DEFAULT_SAMPLE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "sample_employees.xlsx")


def init_session_state():
    """Initializes default session state variables if not already present."""
    if "config" not in st.session_state:
        st.session_state.config = RosterConfig()

    if "employees" not in st.session_state:
        if os.path.exists(DEFAULT_SAMPLE_PATH):
            emps, _ = load_employees_from_excel(DEFAULT_SAMPLE_PATH)
            st.session_state.employees = emps
        else:
            # Fallback 50 dummy employees
            st.session_state.employees = [
                Employee(id=f"EMP{i:03d}", name=f"Employee {i}", active=True)
                for i in range(1, 51)
            ]

    if "start_date" not in st.session_state:
        st.session_state.start_date = date(2026, 11, 1)

    if "end_date" not in st.session_state:
        st.session_state.end_date = date(2026, 11, 30)

    if "current_schedule" not in st.session_state:
        st.session_state.current_schedule = None

    if "feasibility_report" not in st.session_state:
        # Run initial feasibility check
        st.session_state.feasibility_report = run_feasibility_precheck(
            st.session_state.config,
            st.session_state.employees,
            st.session_state.start_date,
            st.session_state.end_date,
        )

    if "historical_result" not in st.session_state:
        st.session_state.historical_result = None

    if "last_status_message" not in st.session_state:
        st.session_state.last_status_message = ""
