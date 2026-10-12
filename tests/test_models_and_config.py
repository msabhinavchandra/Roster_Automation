"""Tests for models, configuration, shift timings, rest calculations, and rule precedence.
"""

from datetime import date, time, datetime
from src.models import (
    DEFAULT_SHIFTS,
    calculate_rest_hours,
    Holiday,
    HolidayPolicy,
)
from src.configuration import RosterConfig, INT_TO_WEEKDAY


def test_editable_staffing_matrix_defaults(default_config):
    """Test 3: Default staffing matrix values and editability."""
    # Sunday (weekday index 6)
    assert default_config.base_matrix[6]["S1"] == 2
    assert default_config.base_matrix[6]["S2"] == 6
    assert default_config.base_matrix[6]["S3"] == 6

    # Monday (0)
    assert default_config.base_matrix[0]["S1"] == 4
    assert default_config.base_matrix[0]["S2"] == 10
    assert default_config.base_matrix[0]["S3"] == 8

    # Wednesday (2) to Saturday (5)
    for wd in [2, 3, 4, 5]:
        assert default_config.base_matrix[wd]["S1"] == 6
        assert default_config.base_matrix[wd]["S2"] == 14
        assert default_config.base_matrix[wd]["S3"] == 16

    # Verify editable
    default_config.base_matrix[6]["S1"] = 3
    assert default_config.base_matrix[6]["S1"] == 3


def test_day_range_rules(default_config):
    """Test 4: Creating, matching, and removing day-range rules."""
    # Wed(2) to Sat(5) rule
    rule = default_config.add_day_range_rule(
        name="Peak Midweek",
        start_weekday=2,
        end_weekday=5,
        shift_mins={"S1": 7, "S2": 15, "S3": 17},
    )
    assert rule.matches_weekday(2)  # Wed
    assert rule.matches_weekday(5)  # Sat
    assert not rule.matches_weekday(0)  # Mon
    assert not rule.matches_weekday(6)  # Sun

    # Rule crossing Sunday boundary: Fri(4) to Mon(0)
    rule_cross = default_config.add_day_range_rule(
        name="Weekend Cross",
        start_weekday=4,
        end_weekday=0,
        shift_mins={"S1": 5},
    )
    assert rule_cross.matches_weekday(4)  # Fri
    assert rule_cross.matches_weekday(6)  # Sun
    assert rule_cross.matches_weekday(0)  # Mon
    assert not rule_cross.matches_weekday(1)  # Tue


def test_rule_precedence(default_config):
    """Test 5 & 6: Precedence order: Date Override > Holiday > Weekday > Day-Range > Base."""
    # Base for Wednesday is S1=6, S2=14, S3=16
    test_wed = date(2026, 11, 4)  # A Wednesday
    assert test_wed.weekday() == 2

    # Level 5: Base Matrix
    staffing, src = default_config.get_effective_staffing(test_wed)
    assert staffing["S1"] == 6
    assert "Base Matrix" in src

    # Level 4: Day-range rule
    default_config.add_day_range_rule("Midweek Boost", 2, 4, {"S1": 8})
    staffing, src = default_config.get_effective_staffing(test_wed)
    assert staffing["S1"] == 8
    assert "Day-Range Rule" in src

    # Level 3: Individual Weekday rule
    default_config.individual_weekday_rules[2] = {"S1": 10, "S2": 14, "S3": 16}
    staffing, src = default_config.get_effective_staffing(test_wed)
    assert staffing["S1"] == 10
    assert "Individual Weekday Rule" in src

    # Level 2: Holiday (e.g. Sunday policy)
    default_config.holidays.append(
        Holiday(date=test_wed, name="Special Holiday", policy=HolidayPolicy.SUNDAY)
    )
    staffing, src = default_config.get_effective_staffing(test_wed)
    assert staffing["S1"] == 2  # Sunday S1 is 2
    assert "Sunday Staffing Policy" in src

    # Level 1: Date Override (Highest)
    default_config.set_date_override(test_wed, {"S1": 15, "S2": 20, "S3": 20}, reason="Critical Launch")
    staffing, src = default_config.get_effective_staffing(test_wed)
    assert staffing["S1"] == 15
    assert "Date Override" in src


def test_shift_timings_and_overnight_timestamps():
    """Test 7: S3 crosses midnight and datetime calculations."""
    d = date(2026, 11, 1)

    s1 = DEFAULT_SHIFTS["S1"]
    assert s1.start_datetime(d) == datetime(2026, 11, 1, 6, 30)
    assert s1.end_datetime(d) == datetime(2026, 11, 1, 15, 30)
    assert s1.duration_hours == 9.0

    s3 = DEFAULT_SHIFTS["S3"]
    assert s3.crosses_midnight is True
    assert s3.start_datetime(d) == datetime(2026, 11, 1, 22, 0)
    # End datetime must be on 2026-11-02 at 07:00!
    assert s3.end_datetime(d) == datetime(2026, 11, 2, 7, 0)
    assert s3.duration_hours == 9.0


def test_rest_calculation_across_off_days():
    """Test 8: Rest calculation across OFF days and consecutive days."""
    # S3 on Friday (ends Saturday 07:00) -> Sat OFF, Sun OFF -> S2 on Monday (starts Mon 14:00)
    # Sat 07:00 to Mon 14:00 = 17 hrs on Sat + 24 hrs on Sun + 14 hrs on Mon = 55.0 hrs
    fri_date = date(2026, 11, 6)
    mon_date = date(2026, 11, 9)
    rest_s3_to_s2 = calculate_rest_hours(fri_date, "S3", mon_date, "S2")
    assert rest_s3_to_s2 == 55.0

    # S2 on Friday (ends Fri 23:00) -> Sat OFF, Sun OFF -> S1 on Monday (starts Mon 06:30)
    # Fri 23:00 to Mon 06:30 = 1 hr on Fri + 24 Sat + 24 Sun + 6.5 Mon = 55.5 hrs
    rest_s2_to_s1 = calculate_rest_hours(fri_date, "S2", mon_date, "S1")
    assert rest_s2_to_s1 == 55.5

    # Same shift consecutive days:
    # S1 on Monday (ends Mon 15:30) -> S1 on Tuesday (starts Tue 06:30) = 15.0 hrs
    tue_date = date(2026, 11, 10)
    rest_s1_consec = calculate_rest_hours(mon_date, "S1", tue_date, "S1")
    assert rest_s1_consec == 15.0
