"""End-to-End tests for Scheduler Modes (Mode B, Mode C) and Historical Analysis.
"""

from datetime import date
from src.models import SchedulingMode, ValidationStatus
from src.scheduler import RosterScheduler
from src.historical_analysis import HistoricalAnalysisResult, parse_and_analyze_historical_roster
from src.excel_handler import export_roster_to_excel


def test_mode_b_full_generation_50_employees(sample_50_employees, default_config):
    """Generates a complete, valid roster for 50 employees over a 14-day period under Mode B."""
    start_d = date(2026, 11, 1)  # Sunday
    end_d = date(2026, 11, 14)   # Saturday (14 days = 2 full cycles)

    scheduler = RosterScheduler(default_config)
    schedule, val_report, msg = scheduler.generate(
        employees=sample_50_employees,
        start_date=start_d,
        end_date=end_d,
        mode=SchedulingMode.MODE_B,
        time_limit_seconds=20,
    )

    assert schedule is not None
    assert val_report.is_valid
    assert val_report.error_count == 0
    assert schedule.solver_status in ("OPTIMAL", "FEASIBLE")

    # Check night shift limit for all employees:
    for e in sample_50_employees:
        s3_count = sum(1 for d in range(14) if schedule.get_assignment(e.id, start_d + date.resolution * d) == "S3")
        assert s3_count <= default_config.monthly_s3_cap


def test_mode_c_fairness_generation(sample_50_employees, default_config):
    """Generates a roster under Mode C (Fairness-Optimized Rotation)."""
    start_d = date(2026, 11, 1)
    end_d = date(2026, 11, 7)    # 7 days

    scheduler = RosterScheduler(default_config)
    schedule, val_report, msg = scheduler.generate(
        employees=sample_50_employees,
        start_date=start_d,
        end_date=end_d,
        mode=SchedulingMode.MODE_C,
        time_limit_seconds=15,
    )

    assert schedule is not None
    assert val_report.is_valid
    assert val_report.error_count == 0


def test_historical_night_shift_counting(tmp_path, sample_50_employees, default_config):
    """Test 23: Historical analysis parses S3 shifts and detects past violations."""
    from src.models import RosterSchedule

    # Create a synthetic historical roster workbook where EMP001 has 12 S3 shifts in Nov 2026
    schedule = RosterSchedule(
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 15),
        employees=sample_50_employees,
    )
    for i in range(12):
        schedule.set_assignment("EMP001", date(2026, 11, 1) + date.resolution * i, "S3")

    test_hist_file = str(tmp_path / "hist_roster.xlsx")
    export_roster_to_excel(
        schedule=schedule,
        config=default_config,
        employees=sample_50_employees,
        output_path=test_hist_file,
    )

    # Parse with historical analysis engine
    hist_result, msgs = parse_and_analyze_historical_roster(test_hist_file, sheet_name="Final Roster", s3_monthly_cap=10)
    assert len(hist_result.all_emp_ids) == 50
    assert len(hist_result.violations_exceeded_s3) >= 1
    viol = next(v for v in hist_result.violations_exceeded_s3 if v["employee_id"] == "EMP001")
    assert viol["s3_count"] == 12
    assert viol["excess"] == 2
