"""Excel Import and Export Handler for Roster Automation.
Handles loading employee workbooks, holiday sheets, historical rosters,
and generating multi-tab professional styled Excel deliverables.
"""

from __future__ import annotations
import io
import os
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from src.models import (
    Employee,
    Holiday,
    HolidayPolicy,
    RosterSchedule,
    ValidationReport,
    FeasibilityReport,
)
from src.configuration import RosterConfig, INT_TO_WEEKDAY


# Styling constants
HEADER_FILL = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
TITLE_FONT = Font(name="Calibri", size=14, bold=True, color="1F497D")
BOLD_FONT = Font(name="Calibri", size=11, bold=True)
NORMAL_FONT = Font(name="Calibri", size=10)

SHIFT_FILLS = {
    "S1": PatternFill(start_color="DCE6F1", end_color="DCE6F1", fill_type="solid"),  # Light Blue
    "S2": PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid"),  # Light Yellow
    "S3": PatternFill(start_color="F2DCDB", end_color="F2DCDB", fill_type="solid"),  # Light Red/Rose
    "OFF": PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid"), # Light Gray
}
SHIFT_FONTS = {
    "S1": Font(name="Calibri", size=10, bold=True, color="1F497D"),
    "S2": Font(name="Calibri", size=10, bold=True, color="7F6000"),
    "S3": Font(name="Calibri", size=10, bold=True, color="953735"),
    "OFF": Font(name="Calibri", size=10, color="595959"),
}

THIN_BORDER = Border(
    left=Side(style="thin", color="D9D9D9"),
    right=Side(style="thin", color="D9D9D9"),
    top=Side(style="thin", color="D9D9D9"),
    bottom=Side(style="thin", color="D9D9D9"),
)


def load_employees_from_excel(
    file_source: Any,
    sheet_name: Optional[str] = None,
    col_mapping: Optional[Dict[str, str]] = None,
) -> Tuple[List[Employee], List[str]]:
    """Loads employees from an Excel file (path or bytes/buffer).
    Supports column mapping, sheet selection, and validation.
    Returns (employees_list, warning_or_error_messages).
    """
    messages = []
    wb = openpyxl.load_workbook(file_source, data_only=True)

    if sheet_name and sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
    else:
        ws = wb.active

    # Read header row
    header = [cell.value for cell in ws[1]]
    header_indices = {str(val).strip(): idx for idx, val in enumerate(header) if val is not None}

    mapping = {
        "id": "Employee_ID",
        "name": "Employee_Name",
        "active": "Active",
        "leave": "Approved_Leave",
    }
    if col_mapping:
        mapping.update(col_mapping)

    id_col = header_indices.get(mapping["id"])
    name_col = header_indices.get(mapping["name"])
    active_col = header_indices.get(mapping["active"])
    leave_col = header_indices.get(mapping["leave"])

    if id_col is None:
        # Fallback search for ID
        id_col = next((idx for name, idx in header_indices.items() if "ID" in name.upper()), None)
    if name_col is None:
        name_col = next((idx for name, idx in header_indices.items() if "NAME" in name.upper()), None)

    if id_col is None or name_col is None:
        messages.append("Could not find Employee_ID and/or Employee_Name columns in worksheet.")
        return [], messages

    employees: List[Employee] = []
    seen_ids = set()

    for row_idx in range(2, ws.max_row + 1):
        row_cells = ws[row_idx]
        emp_id = row_cells[id_col].value
        emp_name = row_cells[name_col].value

        if emp_id is None or str(emp_id).strip() == "":
            continue

        emp_id_str = str(emp_id).strip()
        emp_name_str = str(emp_name).strip() if emp_name is not None else f"Employee {emp_id_str}"

        if emp_id_str in seen_ids:
            messages.append(f"Row {row_idx}: Duplicate Employee_ID '{emp_id_str}' ignored.")
            continue
        seen_ids.add(emp_id_str)

        # Active status
        is_active = True
        if active_col is not None and row_cells[active_col].value is not None:
            val = str(row_cells[active_col].value).strip().lower()
            if val in ("false", "0", "no", "inactive"):
                is_active = False

        # Approved leave parsing if present (comma separated ISO dates)
        approved_leave = set()
        if leave_col is not None and row_cells[leave_col].value is not None:
            leave_raw = str(row_cells[leave_col].value)
            for part in leave_raw.split(","):
                part = part.strip()
                try:
                    dt = datetime.strptime(part, "%Y-%m-%d").date()
                    approved_leave.add(dt)
                except ValueError:
                    pass

        # Collect additional columns
        extra = {}
        for h_name, h_idx in header_indices.items():
            if h_idx not in (id_col, name_col, active_col, leave_col):
                extra[h_name] = row_cells[h_idx].value

        emp = Employee(
            id=emp_id_str,
            name=emp_name_str,
            active=is_active,
            approved_leave=approved_leave,
            extra_attributes=extra,
        )
        employees.append(emp)

    return employees, messages


def create_sample_employees_workbook(
    filepath: str, num_employees: int = 50
) -> str:
    """Generates a real sample employee Excel file with 50 employees."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Employees"

    headers = ["Employee_ID", "Employee_Name", "Active", "Role", "Approved_Leave"]
    ws.append(headers)

    for col_num in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_num)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center")

    for i in range(1, num_employees + 1):
        emp_id = f"EMP{i:03d}"
        emp_name = f"Employee {i}"
        active = True
        role = "Support Engineer"
        # Add sample leave for EMP005 and EMP012
        leave = ""
        if i == 5:
            leave = "2026-11-15, 2026-11-16"
        elif i == 12:
            leave = "2026-11-20"

        ws.append([emp_id, emp_name, active, role, leave])

    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = 20

    wb.save(filepath)
    return filepath


def create_sample_holidays_workbook(filepath: str) -> str:
    """Generates a sample holidays Excel file."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Holidays"

    headers = ["Date", "Holiday_Name", "Description", "Policy", "Custom_S1", "Custom_S2", "Custom_S3"]
    ws.append(headers)

    for col_num in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_num)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center")

    sample_holidays = [
        ("2026-11-04", "Deepavali", "Public Holiday - Deepavali Festival", "SUNDAY", "", "", ""),
        ("2026-11-14", "Children's Day", "Observance", "NORMAL", "", "", ""),
        ("2026-11-25", "Company Foundation Day", "Custom Reduced Operations", "CUSTOM", 3, 8, 8),
    ]

    for h in sample_holidays:
        ws.append(list(h))

    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = 22

    wb.save(filepath)
    return filepath


def export_roster_to_excel(
    schedule: RosterSchedule,
    config: RosterConfig,
    employees: List[Employee],
    feasibility_report: Optional[FeasibilityReport] = None,
    output_path: Optional[str] = None,
    base_workbook_source: Optional[Any] = None,
) -> io.BytesIO:
    """Generates the multi-sheet publication-grade Excel workbook.
    Sheets:
    1. Final Roster
    2. Employee Summary
    3. Daily Shift Coverage
    4. Night Shift Summary
    5. Validation Report
    6. Configuration Summary
    7. Applied Holidays
    8. Feasibility Report

    If base_workbook_source is provided, preserves unrelated existing worksheets.
    """
    if base_workbook_source:
        wb = openpyxl.load_workbook(base_workbook_source)
        # Remove old roster sheets if present
        target_sheets = [
            "Final Roster", "Employee Summary", "Daily Shift Coverage",
            "Night Shift Summary", "Validation Report", "Configuration Summary",
            "Applied Holidays", "Feasibility Report"
        ]
        for ts in target_sheets:
            if ts in wb.sheetnames:
                del wb[ts]
    else:
        wb = openpyxl.Workbook()
        if "Sheet" in wb.sheetnames:
            del wb["Sheet"]

    dates = []
    curr = schedule.start_date
    while curr <= schedule.end_date:
        dates.append(curr)
        curr += timedelta(days=1)

    # 1. TAB: Final Roster
    ws_roster = wb.create_sheet(title="Final Roster", index=0)
    ws_roster.freeze_panes = "C2"

    roster_headers = ["Employee ID", "Employee Name"] + [d.strftime("%Y-%m-%d (%a)") for d in dates]
    ws_roster.append(roster_headers)

    for col_idx in range(1, len(roster_headers) + 1):
        cell = ws_roster.cell(row=1, column=col_idx)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center")

    for row_idx, e in enumerate(employees, start=2):
        row_data = [e.id, e.name]
        for d in dates:
            row_data.append(schedule.get_assignment(e.id, d))
        ws_roster.append(row_data)

        # Apply shift styles
        for col_idx in range(3, len(roster_headers) + 1):
            cell = ws_roster.cell(row=row_idx, column=col_idx)
            val = cell.value
            if val in SHIFT_FILLS:
                cell.fill = SHIFT_FILLS[val]
                cell.font = SHIFT_FONTS[val]
                cell.alignment = Alignment(horizontal="center")
            cell.border = THIN_BORDER

    ws_roster.column_dimensions["A"].width = 15
    ws_roster.column_dimensions["B"].width = 22
    for d_idx in range(len(dates)):
        col_letter = get_column_letter(3 + d_idx)
        ws_roster.column_dimensions[col_letter].width = 16

    # 2. TAB: Employee Summary
    ws_summary = wb.create_sheet(title="Employee Summary")
    ws_summary.append(["Employee ID", "Employee Name", "Status", "S1 Count", "S2 Count", "S3 Count", "Total Working", "Total OFF"])
    for col_idx in range(1, 9):
        c = ws_summary.cell(row=1, column=col_idx)
        c.fill = HEADER_FILL
        c.font = HEADER_FONT
        c.alignment = Alignment(horizontal="center")

    for e in employees:
        s1 = sum(1 for d in dates if schedule.get_assignment(e.id, d) == "S1")
        s2 = sum(1 for d in dates if schedule.get_assignment(e.id, d) == "S2")
        s3 = sum(1 for d in dates if schedule.get_assignment(e.id, d) == "S3")
        off = sum(1 for d in dates if schedule.get_assignment(e.id, d) == "OFF")
        tot = s1 + s2 + s3
        ws_summary.append([e.id, e.name, "Active" if e.active else "Inactive", s1, s2, s3, tot, off])

    for col in ws_summary.columns:
        ws_summary.column_dimensions[get_column_letter(col[0].column)].width = 18

    # 3. TAB: Daily Shift Coverage
    ws_coverage = wb.create_sheet(title="Daily Shift Coverage")
    cov_headers = ["Date", "Weekday", "S1 Req", "S1 Actual", "S2 Req", "S2 Actual", "S3 Req", "S3 Actual", "Total Req", "Total Actual"]
    ws_coverage.append(cov_headers)
    for col_idx in range(1, len(cov_headers) + 1):
        c = ws_coverage.cell(row=1, column=col_idx)
        c.fill = HEADER_FILL
        c.font = HEADER_FONT
        c.alignment = Alignment(horizontal="center")

    eff_matrix = config.get_effective_matrix_for_range(schedule.start_date, schedule.end_date)
    for d in dates:
        req, _ = eff_matrix[d]
        a_s1 = sum(1 for e in employees if schedule.get_assignment(e.id, d) == "S1")
        a_s2 = sum(1 for e in employees if schedule.get_assignment(e.id, d) == "S2")
        a_s3 = sum(1 for e in employees if schedule.get_assignment(e.id, d) == "S3")
        r_s1 = req.get("S1", 0)
        r_s2 = req.get("S2", 0)
        r_s3 = req.get("S3", 0)
        ws_coverage.append([
            d.strftime("%Y-%m-%d"), INT_TO_WEEKDAY[d.weekday()],
            r_s1, a_s1, r_s2, a_s2, r_s3, a_s3,
            r_s1 + r_s2 + r_s3, a_s1 + a_s2 + a_s3
        ])
    for col in ws_coverage.columns:
        ws_coverage.column_dimensions[get_column_letter(col[0].column)].width = 16

    # 4. TAB: Night Shift Summary
    ws_night = wb.create_sheet(title="Night Shift Summary")
    ws_night.append(["Employee ID", "Employee Name", "Month", "S3 Count", "Monthly Cap", "Approaching Limit (>=8)", "Exceeded Limit (>10)"])
    for col_idx in range(1, 8):
        c = ws_night.cell(row=1, column=col_idx)
        c.fill = HEADER_FILL
        c.font = HEADER_FONT
        c.alignment = Alignment(horizontal="center")

    months = sorted(list(set((d.year, d.month) for d in dates)))
    for e in employees:
        for (y, m) in months:
            m_dates = [d for d in dates if d.year == y and d.month == m]
            s3_c = sum(1 for d in m_dates if schedule.get_assignment(e.id, d) == "S3")
            ws_night.append([
                e.id, e.name, f"{y}-{m:02d}", s3_c, config.monthly_s3_cap,
                "YES" if s3_c >= config.monthly_s3_cap - 2 else "NO",
                "YES" if s3_c > config.monthly_s3_cap else "NO"
            ])
    for col in ws_night.columns:
        ws_night.column_dimensions[get_column_letter(col[0].column)].width = 20

    # 5. TAB: Validation Report
    ws_val = wb.create_sheet(title="Validation Report")
    ws_val.append(["Status", "Severity", "Rule Name", "Date", "Employee ID", "Message"])
    for col_idx in range(1, 7):
        c = ws_val.cell(row=1, column=col_idx)
        c.fill = HEADER_FILL
        c.font = HEADER_FONT
        c.alignment = Alignment(horizontal="center")

    if schedule.validation_report:
        for issue in schedule.validation_report.issues:
            ws_val.append([
                schedule.validation_report.status.value,
                issue.severity,
                issue.rule_name,
                issue.date.strftime("%Y-%m-%d") if issue.date else "",
                issue.employee_id or "",
                issue.message
            ])
    for col in ws_val.columns:
        ws_val.column_dimensions[get_column_letter(col[0].column)].width = 25

    # 6. TAB: Configuration Summary
    ws_cfg = wb.create_sheet(title="Configuration Summary")
    ws_cfg.append(["Parameter", "Configured Value", "Notes"])
    for col_idx in range(1, 4):
        c = ws_cfg.cell(row=1, column=col_idx)
        c.fill = HEADER_FILL
        c.font = HEADER_FONT

    cfg_rows = [
        ("Scheduling Mode", schedule.mode.value, "Selected Roster Mode"),
        ("Minimum Rest Period", f"{config.min_rest_hours} hours", "Hard rest requirement between shifts"),
        ("Monthly S3 Cap", f"{config.monthly_s3_cap} shifts", "Hard night shift maximum per calendar month"),
        ("Max 5-Night Blocks / Month", f"{config.max_night_blocks_per_month} blocks", "Consecutive S3 limit"),
        ("Work / OFF Cycle", f"{config.consecutive_work_days} work / {config.consecutive_off_days} off", "Repeating employee cycle"),
        ("S1 Timings", f"{config.shifts['S1'].start_time} - {config.shifts['S1'].end_time}", f"Duration {config.shifts['S1'].duration_hours}h"),
        ("S2 Timings", f"{config.shifts['S2'].start_time} - {config.shifts['S2'].end_time}", f"Duration {config.shifts['S2'].duration_hours}h"),
        ("S3 Timings", f"{config.shifts['S3'].start_time} - {config.shifts['S3'].end_time} (Next Day)", f"Duration {config.shifts['S3'].duration_hours}h"),
    ]
    for r in cfg_rows:
        ws_cfg.append(list(r))
    for col in ws_cfg.columns:
        ws_cfg.column_dimensions[get_column_letter(col[0].column)].width = 30

    # 7. TAB: Applied Holidays
    ws_hol = wb.create_sheet(title="Applied Holidays")
    ws_hol.append(["Date", "Holiday Name", "Description", "Staffing Policy"])
    for col_idx in range(1, 5):
        c = ws_hol.cell(row=1, column=col_idx)
        c.fill = HEADER_FILL
        c.font = HEADER_FONT

    for h in config.holidays:
        ws_hol.append([h.date.strftime("%Y-%m-%d"), h.name, h.description, h.policy.value])
    for col in ws_hol.columns:
        ws_hol.column_dimensions[get_column_letter(col[0].column)].width = 25

    # 8. TAB: Feasibility Report
    ws_feas = wb.create_sheet(title="Feasibility Report")
    ws_feas.append(["Section", "Details"])
    for col_idx in range(1, 3):
        c = ws_feas.cell(row=1, column=col_idx)
        c.fill = HEADER_FILL
        c.font = HEADER_FONT

    if feasibility_report:
        ws_feas.append(["Precheck Status", feasibility_report.status.value])
        for msg in feasibility_report.messages:
            ws_feas.append(["Message", msg])
        for sug in feasibility_report.suggestions:
            ws_feas.append(["Suggestion", sug])
        for k, v in feasibility_report.capacity_metrics.items():
            ws_feas.append([f"Metric: {k}", str(v)])

    for col in ws_feas.columns:
        ws_feas.column_dimensions[get_column_letter(col[0].column)].width = 35

    # Save to buffer
    output_stream = io.BytesIO()
    wb.save(output_stream)
    output_stream.seek(0)

    # Also save to disk if path given
    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(output_stream.getvalue())

    return output_stream
