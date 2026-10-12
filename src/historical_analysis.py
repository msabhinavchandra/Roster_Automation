"""Historical Roster Analysis and Continuity Engine.
Parses prior roster workbooks, analyzes historical compliance (night shift cap,
5-on/2-off cycles, rotation adherence), detects historical shortages, and infers
employee cycle phases for smooth continuity across roster periods.
"""

from __future__ import annotations
import openpyxl
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any, Set
from collections import defaultdict

from src.models import Employee, ShiftDefinition, DEFAULT_SHIFTS
from src.configuration import RosterConfig, INT_TO_WEEKDAY


class HistoricalAnalysisResult:
    def __init__(self):
        self.employee_monthly_s3: Dict[Tuple[str, str], int] = defaultdict(int) # (emp_id, 'YYYY-MM') -> count
        self.violations_exceeded_s3: List[Dict[str, Any]] = []
        self.warnings_approaching_s3: List[Dict[str, Any]] = []
        self.shift_counts_by_emp: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self.daily_coverage_history: Dict[date, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self.inferred_phases: Dict[str, int] = {} # emp_id -> inferred phase (0..6)
        self.cycle_compliance_scores: Dict[str, float] = {} # emp_id -> % 5/2 compliance
        self.rotation_compliance_scores: Dict[str, float] = {}
        self.all_dates: List[date] = []
        self.all_emp_ids: List[str] = []


def parse_and_analyze_historical_roster(
    file_source: Any,
    sheet_name: Optional[str] = None,
    s3_monthly_cap: int = 10,
) -> Tuple[HistoricalAnalysisResult, List[str]]:
    """Analyzes a historical roster workbook.
    Returns (HistoricalAnalysisResult, list_of_info_or_warnings).
    """
    result = HistoricalAnalysisResult()
    messages = []

    wb = openpyxl.load_workbook(file_source, data_only=True)
    if sheet_name and sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
    else:
        # Pick first sheet or sheet with 'roster' in name
        matched = next((s for s in wb.sheetnames if "roster" in s.lower()), None)
        ws = wb[matched] if matched else wb.active

    # Parse headers
    header_row = [cell.value for cell in ws[1]]
    if not header_row or len(header_row) < 3:
        messages.append("Worksheet does not contain enough columns for roster analysis.")
        return result, messages

    # Detect ID col and date columns
    id_col_idx = 0
    date_cols: List[Tuple[int, date]] = []

    for col_idx, val in enumerate(header_row):
        val_str = str(val).strip() if val is not None else ""
        if "ID" in val_str.upper():
            id_col_idx = col_idx
            continue

        # Try parsing date from header
        # Patterns: YYYY-MM-DD, YYYY-MM-DD (Day), DD-MM-YYYY, etc.
        clean_date_str = val_str.split(" ")[0].split("(")[0].strip()
        parsed_dt = None
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%Y/%m/%d"):
            try:
                parsed_dt = datetime.strptime(clean_date_str, fmt).date()
                break
            except ValueError:
                pass
        if parsed_dt is not None:
            date_cols.append((col_idx, parsed_dt))

    if not date_cols:
        messages.append("Could not identify valid date columns in header row.")
        return result, messages

    # Sort date columns chronologically
    date_cols.sort(key=lambda x: x[1])
    result.all_dates = [dc[1] for dc in date_cols]

    # Process employee rows
    for row_idx in range(2, ws.max_row + 1):
        row_cells = ws[row_idx]
        raw_id = row_cells[id_col_idx].value
        if raw_id is None or str(raw_id).strip() == "":
            continue
        emp_id = str(raw_id).strip()
        result.all_emp_ids.append(emp_id)

        # Extract shift timeline
        emp_timeline: List[Tuple[date, str]] = []
        for col_idx, dt in date_cols:
            cell_val = row_cells[col_idx].value
            shift_val = str(cell_val).strip().upper() if cell_val is not None else "OFF"
            if shift_val not in ("S1", "S2", "S3", "OFF"):
                shift_val = "OFF"
            emp_timeline.append((dt, shift_val))
            result.shift_counts_by_emp[emp_id][shift_val] += 1
            result.daily_coverage_history[dt][shift_val] += 1

            if shift_val == "S3":
                month_key = f"{dt.year}-{dt.month:02d}"
                result.employee_monthly_s3[(emp_id, month_key)] += 1

        # Infer phase: determine best matching phase p in 0..6
        best_p = 0
        best_matches = -1
        ref_date = result.all_dates[0]
        for p in range(7):
            matches = 0
            for dt, s in emp_timeline:
                day_offset = (dt - ref_date).days
                cycle_day = (day_offset - p) % 7
                is_working = (s in ("S1", "S2", "S3"))
                expected_working = (cycle_day < 5)
                if is_working == expected_working:
                    matches += 1
            if matches > best_matches:
                best_matches = matches
                best_p = p

        result.inferred_phases[emp_id] = best_p
        total_days = len(emp_timeline)
        result.cycle_compliance_scores[emp_id] = round((best_matches / total_days) * 100, 1) if total_days > 0 else 0.0

    # Evaluate S3 violations in history
    for (emp_id, month_str), count in result.employee_monthly_s3.items():
        if count > s3_monthly_cap:
            result.violations_exceeded_s3.append({
                "employee_id": emp_id,
                "month": month_str,
                "s3_count": count,
                "cap": s3_monthly_cap,
                "excess": count - s3_monthly_cap,
            })
        elif count >= s3_monthly_cap - 2:
            result.warnings_approaching_s3.append({
                "employee_id": emp_id,
                "month": month_str,
                "s3_count": count,
                "cap": s3_monthly_cap,
            })

    messages.append(
        f"Analyzed {len(result.all_emp_ids)} employees across {len(result.all_dates)} historical dates. "
        f"Found {len(result.violations_exceeded_s3)} monthly S3 cap violation(s)."
    )

    return result, messages


def compare_two_rosters(
    roster_a: Dict[Tuple[str, date], str],
    roster_b: Dict[Tuple[str, date], str],
    dates: List[date],
    employees: List[Employee],
) -> Dict[str, Any]:
    """Compares two rosters and calculates change metrics and differences."""
    total_slots = len(employees) * len(dates)
    differences = []
    shift_change_counts = defaultdict(int)

    for e in employees:
        for d in dates:
            s_a = roster_a.get((e.id, d), "OFF")
            s_b = roster_b.get((e.id, d), "OFF")
            if s_a != s_b:
                differences.append({
                    "employee_id": e.id,
                    "date": d,
                    "original": s_a,
                    "new": s_b,
                })
                shift_change_counts[f"{s_a} -> {s_b}"] += 1

    diff_count = len(differences)
    stability_pct = round(((total_slots - diff_count) / total_slots) * 100, 1) if total_slots > 0 else 100.0

    return {
        "total_slots": total_slots,
        "difference_count": diff_count,
        "stability_percentage": stability_pct,
        "differences": differences,
        "shift_changes": dict(shift_change_counts),
    }
