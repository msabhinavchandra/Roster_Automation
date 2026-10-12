"""Centralized Authoritative Validation Pipeline.
Shared across roster generation, manual grid edits, publication, and historical analysis.
Ensures zero-tolerance enforcement of all hard constraints and detailed reporting.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional, Set, Tuple, Any
from collections import defaultdict

from src.models import (
    Employee,
    ShiftDefinition,
    ValidationIssue,
    ValidationReport,
    ValidationStatus,
    RosterSchedule,
    calculate_rest_hours,
)
from src.configuration import RosterConfig, INT_TO_WEEKDAY


def validate_roster(
    schedule: RosterSchedule,
    config: RosterConfig,
    employees: List[Employee],
) -> ValidationReport:
    """Authoritative validation pipeline.
    Validates:
    - Daily shift minimum coverage against effective configuration
    - 5-working-day / 2-OFF-day cycle continuity
    - Shift-block continuity (same shift during work block)
    - Two OFF days following each S3 night-shift block
    - Monthly S3 shift counts (cap = 10)
    - Maximum night blocks per calendar month (cap = 2)
    - Minimum rest hours (default 11.0 hours) calculated from timestamps
    - Overlapping shift assignments
    - Approved leave and availability
    - Inactive employee assignments
    - Duplicate employee IDs

    Returns structured ValidationReport.
    """
    issues: List[ValidationIssue] = []
    metrics: Dict[str, Any] = {}

    start_date = schedule.start_date
    end_date = schedule.end_date
    dates = []
    curr = start_date
    while curr <= end_date:
        dates.append(curr)
        curr += timedelta(days=1)

    emp_dict = {e.id: e for e in employees}

    # 0. Check for duplicate IDs
    seen_ids = set()
    for e in employees:
        if e.id in seen_ids:
            issues.append(
                ValidationIssue(
                    severity="ERROR",
                    rule_name="DUPLICATE_EMPLOYEE_ID",
                    message=f"Duplicate employee ID detected: {e.id}",
                    employee_id=e.id,
                )
            )
        seen_ids.add(e.id)

    # 1. Daily Coverage Validation
    effective_matrix = config.get_effective_matrix_for_range(start_date, end_date)
    daily_coverage = {}
    shift_coverage_totals = defaultdict(int)
    daily_understaffed_count = 0

    for d in dates:
        req_shifts, rule_source = effective_matrix[d]
        assigned_shifts = defaultdict(int)
        for e in employees:
            s = schedule.get_assignment(e.id, d)
            if s in ("S1", "S2", "S3"):
                assigned_shifts[s] += 1
                shift_coverage_totals[s] += 1

        day_cov = {}
        for s in ("S1", "S2", "S3"):
            min_req = req_shifts.get(s, 0)
            actual = assigned_shifts[s]
            day_cov[s] = {"required": min_req, "actual": actual}
            if actual < min_req:
                daily_understaffed_count += 1
                issues.append(
                    ValidationIssue(
                        severity="ERROR",
                        rule_name="UNDERSTAFFED_SHIFT",
                        message=(
                            f"Understaffed on {d} ({INT_TO_WEEKDAY[d.weekday()]}) for {s}: "
                            f"assigned {actual} vs required {min_req} (Deficit: {min_req - actual}). Rule: {rule_source}."
                        ),
                        date=d,
                        shift=s,
                        details={"required": min_req, "actual": actual, "deficit": min_req - actual},
                    )
                )
        daily_coverage[d] = day_cov

    # 2. Inactive Employee Assignments & Approved Leave Violations
    for e in employees:
        for d in dates:
            s = schedule.get_assignment(e.id, d)
            if s != "OFF":
                if not e.active:
                    issues.append(
                        ValidationIssue(
                            severity="ERROR",
                            rule_name="INACTIVE_EMPLOYEE_ASSIGNMENT",
                            message=f"Inactive employee {e.id} ({e.name}) assigned to {s} on {d}.",
                            employee_id=e.id,
                            date=d,
                            shift=s,
                        )
                    )
                if d in e.approved_leave:
                    issues.append(
                        ValidationIssue(
                            severity="ERROR",
                            rule_name="LEAVE_CONFLICT",
                            message=f"Employee {e.id} ({e.name}) assigned to {s} on {d} during approved leave.",
                            employee_id=e.id,
                            date=d,
                            shift=s,
                        )
                    )
                if d in e.shift_availability and s not in e.shift_availability[d]:
                    issues.append(
                        ValidationIssue(
                            severity="ERROR",
                            rule_name="UNAVAILABLE_SHIFT",
                            message=f"Employee {e.id} ({e.name}) assigned to {s} on {d} when shift is unavailable.",
                            employee_id=e.id,
                            date=d,
                            shift=s,
                        )
                    )

    # 3. Work/OFF Cycle, Shift Block Continuity & Post-Night OFF Days
    emp_monthly_s3 = defaultdict(lambda: defaultdict(int))  # (emp_id, (year, month)) -> count
    emp_night_blocks = defaultdict(lambda: defaultdict(int)) # (emp_id, (year, month)) -> block count
    emp_approaching_s3 = []
    emp_exceeded_s3 = []

    for e in employees:
        if not e.active:
            continue

        emp_assignments = [schedule.get_assignment(e.id, d) for d in dates]

        # Extract contiguous working blocks and off blocks
        i = 0
        n = len(dates)
        while i < n:
            curr_shift = emp_assignments[i]
            if curr_shift == "OFF":
                # Scan OFF block
                off_start = i
                while i < n and emp_assignments[i] == "OFF":
                    i += 1
                off_len = i - off_start
                # OFF block check
                if (off_len > config.consecutive_off_days) or (off_start > 0 and i < n and off_len != config.consecutive_off_days):
                    issues.append(
                        ValidationIssue(
                            severity="ERROR",
                            rule_name="OFF_CYCLE_LENGTH_VIOLATION",
                            message=(
                                f"Employee {e.id} has {off_len} consecutive OFF days "
                                f"from {dates[off_start]} to {dates[i-1]} (Expected {config.consecutive_off_days})."
                            ),
                            employee_id=e.id,
                            date=dates[off_start],
                        )
                    )
            else:
                # Scan Work block
                work_start = i
                block_shift = curr_shift
                is_mixed_block = False
                has_s3 = (curr_shift == "S3")

                while i < n and emp_assignments[i] != "OFF":
                    if emp_assignments[i] != block_shift:
                        is_mixed_block = True
                    if emp_assignments[i] == "S3":
                        has_s3 = True
                    i += 1
                work_len = i - work_start

                # Mixed shift in work block
                if is_mixed_block:
                    issues.append(
                        ValidationIssue(
                            severity="ERROR",
                            rule_name="SHIFT_BLOCK_MIXED_SHIFTS",
                            message=(
                                f"Employee {e.id} worked mixed shifts in work block from "
                                f"{dates[work_start]} to {dates[i-1]}. Work blocks must be the same shift."
                            ),
                            employee_id=e.id,
                            date=dates[work_start],
                        )
                    )

                # Work block length check: must not exceed max days, and if surrounded by OFF days must equal 5
                if (work_len > config.consecutive_work_days) or (work_start > 0 and i < n and work_len != config.consecutive_work_days):
                    issues.append(
                        ValidationIssue(
                            severity="ERROR",
                            rule_name="WORK_CYCLE_LENGTH_VIOLATION",
                            message=(
                                f"Employee {e.id} has {work_len} consecutive working days from "
                                f"{dates[work_start]} to {dates[i-1]} (Expected {config.consecutive_work_days})."
                            ),
                            employee_id=e.id,
                            date=dates[work_start],
                        )
                    )

                # Post-Night Shift OFF Days requirement:
                if has_s3:
                    # After this S3 block, must have at least 2 consecutive OFF days
                    if i < n:
                        # Check following days
                        post_off_len = 0
                        k = i
                        while k < n and emp_assignments[k] == "OFF":
                            post_off_len += 1
                            k += 1
                        if post_off_len < config.consecutive_off_days and k < n:
                            issues.append(
                                ValidationIssue(
                                    severity="ERROR",
                                    rule_name="NIGHT_BLOCK_OFF_DAYS_VIOLATION",
                                    message=(
                                        f"Employee {e.id} completed S3 night block ending {dates[i-1]} "
                                        f"but did not receive {config.consecutive_off_days} consecutive OFF days before next assignment."
                                    ),
                                    employee_id=e.id,
                                    date=dates[i-1],
                                )
                            )

                    # Record night block for the month of block start
                    block_month = (dates[work_start].year, dates[work_start].month)
                    emp_night_blocks[e.id][block_month] += 1

        # Count monthly S3 shifts
        for d, s in zip(dates, emp_assignments):
            if s == "S3":
                emp_monthly_s3[e.id][(d.year, d.month)] += 1

        # Rest Period Checks between consecutive work assignments
        work_indices = [idx for idx, s in enumerate(emp_assignments) if s != "OFF"]
        for idx_w in range(len(work_indices) - 1):
            i1 = work_indices[idx_w]
            i2 = work_indices[idx_w + 1]
            d1 = dates[i1]
            d2 = dates[i2]
            s1 = emp_assignments[i1]
            s2 = emp_assignments[i2]

            rest_hours = calculate_rest_hours(d1, s1, d2, s2, config.shifts)
            if rest_hours < config.min_rest_hours:
                issues.append(
                    ValidationIssue(
                        severity="ERROR",
                        rule_name="MINIMUM_REST_VIOLATION",
                        message=(
                            f"Rest violation for {e.id}: only {rest_hours:.1f} hours rest between {s1} on {d1} "
                            f"(ends {config.shifts[s1].end_datetime(d1).strftime('%Y-%m-%d %H:%M')}) and "
                            f"{s2} on {d2} (starts {config.shifts[s2].start_datetime(d2).strftime('%Y-%m-%d %H:%M')}). "
                            f"Required minimum: {config.min_rest_hours:.1f} hours."
                        ),
                        employee_id=e.id,
                        date=d2,
                        shift=s2,
                        details={"actual_rest": rest_hours, "required_rest": config.min_rest_hours},
                    )
                )

    # 4. Monthly Night Cap & Night Block Cap Checks
    for e in employees:
        for (year, month), s3_count in emp_monthly_s3[e.id].items():
            month_str = f"{year}-{month:02d}"
            if s3_count > config.monthly_s3_cap:
                emp_exceeded_s3.append((e.id, month_str, s3_count))
                issues.append(
                    ValidationIssue(
                        severity="ERROR",
                        rule_name="MONTHLY_S3_CAP_EXCEEDED",
                        message=(
                            f"Night cap violation: Employee {e.id} assigned {s3_count} S3 shifts "
                            f"in {month_str} (Hard limit: {config.monthly_s3_cap})."
                        ),
                        employee_id=e.id,
                        details={"count": s3_count, "cap": config.monthly_s3_cap, "month": month_str},
                    )
                )
            elif s3_count >= config.monthly_s3_cap - 2:
                emp_approaching_s3.append((e.id, month_str, s3_count))
                issues.append(
                    ValidationIssue(
                        severity="WARNING",
                        rule_name="MONTHLY_S3_CAP_APPROACHING",
                        message=(
                            f"Night cap warning: Employee {e.id} assigned {s3_count}/{config.monthly_s3_cap} "
                            f"S3 shifts in {month_str}."
                        ),
                        employee_id=e.id,
                        details={"count": s3_count, "cap": config.monthly_s3_cap, "month": month_str},
                    )
                )

        for (year, month), block_count in emp_night_blocks[e.id].items():
            month_str = f"{year}-{month:02d}"
            if block_count > config.max_night_blocks_per_month:
                issues.append(
                    ValidationIssue(
                        severity="ERROR",
                        rule_name="MONTHLY_NIGHT_BLOCKS_EXCEEDED",
                        message=(
                            f"Employee {e.id} assigned {block_count} night-shift blocks in {month_str} "
                            f"(Limit: {config.max_night_blocks_per_month})."
                        ),
                        employee_id=e.id,
                        details={"count": block_count, "limit": config.max_night_blocks_per_month},
                    )
                )

    has_errors = any(i.severity == "ERROR" for i in issues)
    status = ValidationStatus.INVALID if has_errors else ValidationStatus.VALID

    metrics = {
        "daily_coverage": daily_coverage,
        "shift_coverage_totals": dict(shift_coverage_totals),
        "emp_monthly_s3": {
            f"{emp_id}_{ym[0]}-{ym[1]:02d}": cnt
            for emp_id, m_dict in emp_monthly_s3.items()
            for ym, cnt in m_dict.items()
        },
        "emp_exceeded_s3_count": len(emp_exceeded_s3),
        "emp_approaching_s3_count": len(emp_approaching_s3),
        "total_errors": sum(1 for i in issues if i.severity == "ERROR"),
        "total_warnings": sum(1 for i in issues if i.severity == "WARNING"),
        "total_assigned_working_shifts": sum(shift_coverage_totals.values()),
    }

    return ValidationReport(
        status=status,
        issues=issues,
        metrics=metrics,
    )
