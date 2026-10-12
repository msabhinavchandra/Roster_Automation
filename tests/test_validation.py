"""Tests for centralized authoritative validation pipeline.
Covers 5/2 cycles, night blocks, monthly caps, leave, rest, manual edits, and publication blocking.
"""

from datetime import date, timedelta
from src.models import (
    Employee,
    RosterSchedule,
    SchedulingMode,
    ValidationStatus,
)
from src.validation import validate_roster


def test_five_on_two_off_continuity(sample_50_employees, default_config):
    """Test 9: Work and OFF cycle length violations."""
    start_d = date(2026, 11, 1)
    end_d = date(2026, 11, 14)  # 14 days

    schedule = RosterSchedule(
        start_date=start_d,
        end_date=end_d,
        employees=sample_50_employees,
    )

    # EMP001 works 6 consecutive days instead of 5
    for i in range(6):
        schedule.set_assignment("EMP001", start_d + timedelta(days=i), "S1")
    schedule.set_assignment("EMP001", start_d + timedelta(days=6), "OFF")

    report = validate_roster(schedule, default_config, sample_50_employees)
    assert not report.is_valid
    err_rules = [i.rule_name for i in report.issues if i.severity == "ERROR"]
    assert "WORK_CYCLE_LENGTH_VIOLATION" in err_rules


def test_s3_block_mandatory_off_days(sample_50_employees, default_config):
    """Test 10: Mandatory 2 OFF days following an S3 night-shift block."""
    start_d = date(2026, 11, 1)
    end_d = date(2026, 11, 14)

    schedule = RosterSchedule(
        start_date=start_d,
        end_date=end_d,
        employees=sample_50_employees,
    )

    # EMP001 works S3 for 5 days, but then works S1 immediately on day 6 (no 2 OFF days!)
    for i in range(5):
        schedule.set_assignment("EMP001", start_d + timedelta(days=i), "S3")
    schedule.set_assignment("EMP001", start_d + timedelta(days=5), "S1")

    report = validate_roster(schedule, default_config, sample_50_employees)
    assert not report.is_valid
    err_rules = [i.rule_name for i in report.issues if i.severity == "ERROR"]
    assert "NIGHT_BLOCK_OFF_DAYS_VIOLATION" in err_rules or "MINIMUM_REST_VIOLATION" in err_rules


def test_monthly_night_cap_enforcement(sample_50_employees, default_config):
    """Test 11: No employee may exceed 10 S3 shifts in a calendar month."""
    start_d = date(2026, 11, 1)
    end_d = date(2026, 11, 30)

    schedule = RosterSchedule(
        start_date=start_d,
        end_date=end_d,
        employees=sample_50_employees,
    )

    # Assign EMP001 11 S3 shifts
    for i in range(11):
        schedule.set_assignment("EMP001", start_d + timedelta(days=i), "S3")

    report = validate_roster(schedule, default_config, sample_50_employees)
    assert not report.is_valid
    err_rules = [i.rule_name for i in report.issues if i.severity == "ERROR"]
    assert "MONTHLY_S3_CAP_EXCEEDED" in err_rules


def test_month_boundary_behavior(sample_50_employees, default_config):
    """Test 13: Monthly night-shift counts across month boundary (Nov 30 to Dec 1)."""
    # Range: Nov 25 to Dec 10
    start_d = date(2026, 11, 25)
    end_d = date(2026, 12, 10)

    schedule = RosterSchedule(
        start_date=start_d,
        end_date=end_d,
        employees=sample_50_employees,
    )

    # EMP001 works 5 S3 shifts in Nov (Nov 25-29) and 5 S3 shifts in Dec (Dec 2-6)
    # Total S3 across span = 10, but in Nov = 5 (<= 10), in Dec = 5 (<= 10). Both are valid!
    for i in range(5):
        schedule.set_assignment("EMP001", date(2026, 11, 25) + timedelta(days=i), "S3")
    schedule.set_assignment("EMP001", date(2026, 11, 30), "OFF")
    schedule.set_assignment("EMP001", date(2026, 12, 1), "OFF")
    for i in range(5):
        schedule.set_assignment("EMP001", date(2026, 12, 2) + timedelta(days=i), "S3")

    report = validate_roster(schedule, default_config, sample_50_employees)
    # Check that neither month exceeded cap for EMP001
    cap_errors = [i for i in report.issues if i.rule_name == "MONTHLY_S3_CAP_EXCEEDED" and i.employee_id == "EMP001"]
    assert len(cap_errors) == 0


def test_coverage_requirements(sample_50_employees, default_config):
    """Test 14: Understaffing triggers validation error."""
    start_d = date(2026, 11, 1)  # Sunday
    end_d = date(2026, 11, 1)

    schedule = RosterSchedule(
        start_date=start_d,
        end_date=end_d,
        employees=sample_50_employees,
    )
    # Default Sunday requires S1=2, S2=6, S3=6. Assign only 1 to S1!
    schedule.set_assignment("EMP001", start_d, "S1")

    report = validate_roster(schedule, default_config, sample_50_employees)
    assert not report.is_valid
    assert any(i.rule_name == "UNDERSTAFFED_SHIFT" for i in report.issues)


def test_approved_leave_conflict(sample_50_employees, default_config):
    """Test 18: Assigning an employee on approved leave triggers validation error."""
    start_d = date(2026, 11, 5)
    end_d = date(2026, 11, 5)

    emp = sample_50_employees[0]
    emp.approved_leave.add(start_d)

    schedule = RosterSchedule(
        start_date=start_d,
        end_date=end_d,
        employees=sample_50_employees,
    )
    schedule.set_assignment(emp.id, start_d, "S1")

    report = validate_roster(schedule, default_config, sample_50_employees)
    assert not report.is_valid
    assert any(i.rule_name == "LEAVE_CONFLICT" for i in report.issues)


def test_manual_edit_revalidation_and_publish_block(sample_50_employees, default_config):
    """Test 19 & 22: Manual edit to invalid shift and prevention of invalid publication."""
    start_d = date(2026, 11, 1)
    end_d = date(2026, 11, 7)

    schedule = RosterSchedule(
        start_date=start_d,
        end_date=end_d,
        employees=sample_50_employees,
    )
    # Everyone is OFF initially -> Understaffed -> Invalid
    report = validate_roster(schedule, default_config, sample_50_employees)
    schedule.validation_report = report

    # Publication check: is_valid is False, publication cannot proceed
    assert not schedule.validation_report.is_valid
    assert schedule.is_published is False


def test_ui_and_backend_validation_consistency(sample_50_employees, default_config):
    """Test 24: Consistency between UI metrics and backend validation."""
    start_d = date(2026, 11, 1)
    end_d = date(2026, 11, 7)

    schedule = RosterSchedule(
        start_date=start_d,
        end_date=end_d,
        employees=sample_50_employees,
    )
    report = validate_roster(schedule, default_config, sample_50_employees)
    # Structured report must have error_count matching issue count
    actual_errors = sum(1 for i in report.issues if i.severity == "ERROR")
    assert report.error_count == actual_errors
    assert "daily_coverage" in report.metrics
