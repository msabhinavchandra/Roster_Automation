"""Tests for immediate feasibility prechecks, solver-proven infeasibility, and timeout handling.
"""

from datetime import date
from src.models import FeasibilityStatus, SchedulingMode, ValidationStatus
from src.feasibility import run_feasibility_precheck
from src.scheduler import RosterScheduler


def test_feasibility_precheck_daily_shortage(sample_20_employees, default_config):
    """Test 15a: Daily staffing requirement exceeds active available employees."""
    # 20 employees available, but Wednesday requires 6 + 14 + 16 = 36 employees
    start_d = date(2026, 11, 4)  # Wednesday
    end_d = date(2026, 11, 4)

    report = run_feasibility_precheck(default_config, sample_20_employees, start_d, end_d)
    assert report.status == FeasibilityStatus.INFEASIBLE
    assert any("exceeds available" in m.lower() for m in report.messages)
    assert len(report.shortages) > 0
    assert report.shortages[0]["shortage"] == 36 - 20  # 16 shortage


def test_feasibility_precheck_weekly_capacity(sample_20_employees, default_config):
    """Test 15b: Insufficient aggregate work capacity across a 7-day period."""
    start_d = date(2026, 11, 2)  # Monday
    end_d = date(2026, 11, 8)    # Sunday (7 days)

    # 20 employees * 5 days/wk = 100 max employee-days
    # Default weekly demand = 202 shifts
    report = run_feasibility_precheck(default_config, sample_20_employees, start_d, end_d)
    assert report.status == FeasibilityStatus.INFEASIBLE
    assert any("aggregate employee capacity" in m.lower() for m in report.messages)


def test_feasibility_precheck_monthly_s3_capacity(sample_20_employees, default_config):
    """Test 15c: Required S3 night shifts exceed active * monthly_s3_cap."""
    # In 30 days (Nov 1 to Nov 30), total S3 demand is ~370 shifts
    # 20 employees * 10 max S3 = 200 shifts max capacity
    start_d = date(2026, 11, 1)
    end_d = date(2026, 11, 30)

    report = run_feasibility_precheck(default_config, sample_20_employees, start_d, end_d)
    assert report.status == FeasibilityStatus.INFEASIBLE
    assert any("monthly limit" in m.lower() for m in report.messages)


def test_solver_proven_infeasibility(sample_50_employees, default_config):
    """Test 16: CP-SAT proves problem is infeasible under contradictory constraints."""
    start_d = date(2026, 11, 1)
    end_d = date(2026, 11, 7)  # 1 week

    # Pin EMP001 to work on day 0 (phase 0) but forbid all working shifts via empty availability
    emp = sample_50_employees[0]
    emp.initial_phase = 0
    emp.shift_availability[start_d] = []  # No working shifts permitted

    scheduler = RosterScheduler(default_config)
    schedule, report, msg = scheduler.generate(
        employees=sample_50_employees,
        start_date=start_d,
        end_date=end_d,
        mode=SchedulingMode.MODE_B,
        time_limit_seconds=5,
    )
    assert schedule is None
    assert report.status == ValidationStatus.INFEASIBLE
    assert "infeasible" in msg.lower()


def test_solver_timeout_handling(sample_50_employees, default_config, monkeypatch):
    """Test 17: Solver timeout returns UNRESOLVED rather than false infeasibility."""
    from ortools.sat.python import cp_model

    # Mock Solve to return UNKNOWN (simulating timeout)
    original_solve = cp_model.CpSolver.Solve

    def mock_solve(self, model):
        return cp_model.UNKNOWN

    monkeypatch.setattr(cp_model.CpSolver, "Solve", mock_solve)

    scheduler = RosterScheduler(default_config)
    schedule, report, msg = scheduler.generate(
        employees=sample_50_employees,
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 7),
        mode=SchedulingMode.MODE_B,
        time_limit_seconds=1,
    )

    assert schedule is None
    assert report.status == ValidationStatus.UNRESOLVED
    assert "timed out" in msg.lower() or "unresolved" in msg.lower()
