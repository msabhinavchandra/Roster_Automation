"""Immediate Feasibility Analysis Engine.
Provides instant mathematical capacity prechecks and diagnostic explanations
before generating a full roster.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict

from src.models import (
    FeasibilityReport,
    FeasibilityStatus,
    Employee,
    ShiftDefinition,
)
from src.configuration import RosterConfig, INT_TO_WEEKDAY


def run_feasibility_precheck(
    config: RosterConfig,
    employees: List[Employee],
    start_date: date,
    end_date: date,
) -> FeasibilityReport:
    """Performs immediate mathematical necessary-condition checks.
    Does not invoke the full solver; runs in milliseconds.
    Returns structured FeasibilityReport with status and plain-language diagnostic messages.
    """
    messages: List[str] = []
    shortages: List[Dict[str, Any]] = []
    suggestions: List[str] = []
    is_infeasible = False

    active_employees = [e for e in employees if e.active]
    num_active = len(active_employees)

    if num_active == 0:
        return FeasibilityReport(
            status=FeasibilityStatus.INFEASIBLE,
            messages=["No active employees available in the roster pool."],
            shortages=[{"type": "NO_ACTIVE_EMPLOYEES", "shortage": 1}],
            suggestions=["Activate employees in the Employee Management tab or upload a valid employee workbook."],
        )

    # 1. Date-by-date staffing vs active available employees
    curr = start_date
    daily_staffing_map = config.get_effective_matrix_for_range(start_date, end_date)

    daily_shortages = []
    total_required_assignments = 0
    shift_totals: Dict[str, int] = defaultdict(int)
    monthly_s3_required: Dict[Tuple[int, int], int] = defaultdict(int)

    while curr <= end_date:
        staffing_dict, source = daily_staffing_map[curr]
        s1_req = staffing_dict.get("S1", 0)
        s2_req = staffing_dict.get("S2", 0)
        s3_req = staffing_dict.get("S3", 0)
        daily_req = s1_req + s2_req + s3_req

        total_required_assignments += daily_req
        shift_totals["S1"] += s1_req
        shift_totals["S2"] += s2_req
        shift_totals["S3"] += s3_req

        month_key = (curr.year, curr.month)
        monthly_s3_required[month_key] += s3_req

        # Employees on approved leave on this date
        on_leave_count = sum(1 for e in active_employees if curr in e.approved_leave)
        available_today = num_active - on_leave_count

        if daily_req > available_today:
            shortage = daily_req - available_today
            daily_shortages.append({
                "date": curr,
                "weekday": INT_TO_WEEKDAY[curr.weekday()],
                "required": daily_req,
                "available": available_today,
                "on_leave": on_leave_count,
                "shortage": shortage,
                "rule_source": source,
            })
            is_infeasible = True

        curr += timedelta(days=1)

    if daily_shortages:
        max_daily_shortage = max(d["shortage"] for d in daily_shortages)
        sample_dates = ", ".join(f"{d['date']} ({d['weekday']}: req {d['required']} vs avail {d['available']})" for d in daily_shortages[:3])
        messages.append(
            f"Daily headcount requirement exceeds available active employees on {len(daily_shortages)} date(s). "
            f"Sample conflicts: {sample_dates}. Maximum daily shortage: {max_daily_shortage} employees."
        )
        shortages.extend(daily_shortages)
        suggestions.append(
            f"Reduce daily shift minimums by at least {max_daily_shortage} on peak days, or increase active headcount by {max_daily_shortage}."
        )

    # 2. Total work capacity vs required work-days (5-on / 2-off cycle bound)
    # In any period of D days, an employee can work at most ceil(D * 5 / 7) days under strict 5/2 cycle.
    total_days = (end_date - start_date).days + 1
    max_days_per_emp = (total_days * config.consecutive_work_days) / (config.consecutive_work_days + config.consecutive_off_days)
    theoretical_total_capacity = int(num_active * max_days_per_emp)

    # Deduct approved leave days
    total_leave_days = sum(
        sum(1 for d in e.approved_leave if start_date <= d <= end_date)
        for e in active_employees
    )
    effective_total_capacity = theoretical_total_capacity - total_leave_days

    if total_required_assignments > effective_total_capacity:
        cap_shortage = total_required_assignments - effective_total_capacity
        is_infeasible = True
        messages.append(
            f"Total required shift assignments ({total_required_assignments}) exceeds aggregate employee capacity "
            f"({effective_total_capacity} employee-days based on {config.consecutive_work_days}/"
            f"{config.consecutive_off_days} cycle and {total_leave_days} approved leave days). "
            f"Net capacity shortfall: {cap_shortage} shifts across {total_days} days."
        )
        shortages.append({"type": "TOTAL_WORK_CAPACITY", "shortage": cap_shortage})
        suggestions.append(
            f"Reduce overall shift minimums by {cap_shortage} shifts across the period, or add at least "
            f"{int((cap_shortage / max_days_per_emp) + 0.99)} more active employees."
        )

    # 3. Monthly Night Shift (S3) Capacity Check
    for (year, month), s3_req in monthly_s3_required.items():
        max_s3_allowed = num_active * config.monthly_s3_cap
        if s3_req > max_s3_allowed:
            s3_shortage = s3_req - max_s3_allowed
            is_infeasible = True
            messages.append(
                f"Required S3 night shifts in {year}-{month:02d} ({s3_req}) exceeds the absolute monthly limit "
                f"({max_s3_allowed} shifts = {num_active} employees × {config.monthly_s3_cap} max S3/month). "
                f"Night shift deficit: {s3_shortage} shifts."
            )
            shortages.append({
                "type": "MONTHLY_S3_CAP_EXCEEDED",
                "month": f"{year}-{month:02d}",
                "required_s3": s3_req,
                "max_allowed": max_s3_allowed,
                "shortage": s3_shortage,
            })
            suggestions.append(
                f"For {year}-{month:02d}, reduce S3 night staffing requirements by {s3_shortage} shifts, "
                f"or increase employee pool by {int((s3_shortage / config.monthly_s3_cap) + 0.99)} staff."
            )

    # 4. Weekly Night Shift Block Compatibility Check
    # A 5-night block followed by 2 OFF days takes 7 days.
    # In any 7-day period, an employee assigned to an S3 block works 5 nights.
    # The maximum simultaneous S3 blocks that can run without exceeding active headcount is num_active.
    # Furthermore, on any day, the S3 required cannot exceed the number of active employees.
    max_daily_s3 = max((daily_staffing_map[d][0].get("S3", 0) for d in daily_staffing_map), default=0)
    if max_daily_s3 > num_active:
        is_infeasible = True
        s3_peak_shortage = max_daily_s3 - num_active
        messages.append(
            f"Peak daily S3 requirement ({max_daily_s3}) exceeds total active employees ({num_active}). "
            f"Shortage: {s3_peak_shortage} employees."
        )
        suggestions.append(f"Reduce peak daily S3 requirement below {num_active}.")

    # 5. Rest period verification
    for shift_code, shift_def in config.shifts.items():
        if shift_def.duration_hours < 1.0 or shift_def.duration_hours > 16.0:
            messages.append(f"Shift {shift_code} has abnormal duration of {shift_def.duration_hours:.1f} hours.")
            suggestions.append("Check shift start and end times in configuration.")

    status = FeasibilityStatus.INFEASIBLE if is_infeasible else FeasibilityStatus.FEASIBLE_BY_PRECHECK

    if not is_infeasible:
        messages.append(
            f"Precheck passed: Total demand ({total_required_assignments} shifts) is within available capacity "
            f"({effective_total_capacity} employee-days). Monthly S3 requirements are within the configured cap."
        )

    capacity_metrics = {
        "num_active_employees": num_active,
        "total_days": total_days,
        "total_required_assignments": total_required_assignments,
        "effective_total_capacity": effective_total_capacity,
        "shift_totals": dict(shift_totals),
        "monthly_s3_required": {f"{y}-{m:02d}": req for (y, m), req in monthly_s3_required.items()},
        "max_monthly_s3_capacity": num_active * config.monthly_s3_cap,
        "average_weekly_required": round(total_required_assignments * 7.0 / total_days, 1) if total_days > 0 else 0,
        "average_weekly_s3_required": round(shift_totals["S3"] * 7.0 / total_days, 1) if total_days > 0 else 0,
    }

    return FeasibilityReport(
        status=status,
        messages=messages,
        shortages=shortages,
        capacity_metrics=capacity_metrics,
        suggestions=suggestions,
    )
