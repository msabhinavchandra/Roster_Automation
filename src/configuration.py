"""Configuration and Rule Precedence Engine for Roster Automation.
Manages shift definitions, base matrix, weekday-range rules, date overrides,
precedence resolution, and application settings.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, time, timedelta
from typing import Dict, List, Optional, Tuple, Any
import copy

from src.models import (
    ShiftDefinition,
    DEFAULT_SHIFTS,
    DayRangeRule,
    DateOverrideRule,
    Holiday,
    HolidayPolicy,
    SchedulingMode,
)

# Weekday constants (Python convention: 0 = Monday, 6 = Sunday)
WEEKDAY_NAMES = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]
WEEKDAY_TO_INT = {name: i for i, name in enumerate(WEEKDAY_NAMES)}
INT_TO_WEEKDAY = {i: name for i, name in enumerate(WEEKDAY_NAMES)}

# Default Base Staffing Matrix per weekday
# Sunday: 2, 6, 6
# Monday: 4, 10, 8
# Tuesday: 4, 10, 8
# Wednesday..Saturday: 6, 14, 16
DEFAULT_BASE_MATRIX: Dict[int, Dict[str, int]] = {
    0: {"S1": 4, "S2": 10, "S3": 8},   # Monday
    1: {"S1": 4, "S2": 10, "S3": 8},   # Tuesday
    2: {"S1": 6, "S2": 14, "S3": 16},  # Wednesday
    3: {"S1": 6, "S2": 14, "S3": 16},  # Thursday
    4: {"S1": 6, "S2": 14, "S3": 16},  # Friday
    5: {"S1": 6, "S2": 14, "S3": 16},  # Saturday
    6: {"S1": 2, "S2": 6, "S3": 6},    # Sunday
}


@dataclass
class HeadcountPreferences:
    """Soft headcount targets by day category."""
    sunday_preference: str = "LOWEST"
    mon_tue_preference: str = "MEDIUM"
    wed_sat_preference: str = "HIGHEST"
    # Weight factors for solver objective
    weight_unnecessary_excess: int = 10
    weight_fairness_night: int = 20
    weight_fairness_weekend: int = 15
    weight_rotation_preference: int = 25


@dataclass
class RosterConfig:
    shifts: Dict[str, ShiftDefinition] = field(default_factory=lambda: copy.deepcopy(DEFAULT_SHIFTS))
    base_matrix: Dict[int, Dict[str, int]] = field(default_factory=lambda: copy.deepcopy(DEFAULT_BASE_MATRIX))
    day_range_rules: List[DayRangeRule] = field(default_factory=list)
    individual_weekday_rules: Dict[int, Dict[str, int]] = field(default_factory=dict)
    date_overrides: Dict[date, DateOverrideRule] = field(default_factory=dict)
    holidays: List[Holiday] = field(default_factory=list)

    # Core constraint parameters
    min_rest_hours: float = 11.0
    monthly_s3_cap: int = 10
    max_night_blocks_per_month: int = 2
    consecutive_work_days: int = 5
    consecutive_off_days: int = 2

    # Headcount preferences & weights
    headcount_preferences: HeadcountPreferences = field(default_factory=HeadcountPreferences)

    # Solver configuration
    mode: SchedulingMode = SchedulingMode.MODE_B
    solver_time_limit_seconds: int = 30
    random_seed: int = 42
    output_filename: str = "output/roster_generated.xlsx"

    def get_effective_staffing(self, target_date: date) -> Tuple[Dict[str, int], str]:
        """Resolves the effective minimum staffing for a specific date using strict precedence:
        1. Explicit date-specific staffing override (Highest)
        2. Applied holiday policy (if date is a holiday)
        3. Explicit individual-weekday rules
        4. Applicable weekday-range rules (most recently created / first matching)
        5. Base default matrix (Lowest)

        Returns (shift_mins_dict, explanation_source).
        """
        # 1. Date-specific override
        if target_date in self.date_overrides:
            override = self.date_overrides[target_date]
            return copy.deepcopy(override.shift_mins), f"Date Override ({override.reason or 'User Override'})"

        # 2. Holiday Policy
        matching_holiday = next((h for h in self.holidays if h.date == target_date), None)
        if matching_holiday:
            if matching_holiday.policy == HolidayPolicy.SUNDAY:
                return copy.deepcopy(self.base_matrix[6]), f"Holiday: {matching_holiday.name} (Sunday Staffing Policy)"
            elif matching_holiday.policy == HolidayPolicy.CUSTOM and matching_holiday.custom_shift_mins:
                return copy.deepcopy(matching_holiday.custom_shift_mins), f"Holiday: {matching_holiday.name} (Custom Policy)"
            # If NORMAL policy, continue to standard rules

        weekday = target_date.weekday()

        # 3. Explicit individual-weekday rule
        if weekday in self.individual_weekday_rules and self.individual_weekday_rules[weekday]:
            return copy.deepcopy(self.individual_weekday_rules[weekday]), f"Individual Weekday Rule ({INT_TO_WEEKDAY[weekday]})"

        # 4. Applicable weekday-range rules
        for rule in self.day_range_rules:
            if rule.active and rule.matches_weekday(weekday):
                # Construct effective by starting with base and overlaying rule shifts
                merged = copy.deepcopy(self.base_matrix[weekday])
                merged.update(rule.shift_mins)
                return merged, f"Day-Range Rule: {rule.name}"

        # 5. Base default matrix
        return copy.deepcopy(self.base_matrix[weekday]), f"Base Matrix ({INT_TO_WEEKDAY[weekday]})"

    def get_effective_matrix_for_range(
        self, start_date: date, end_date: date
    ) -> Dict[date, Tuple[Dict[str, int], str]]:
        """Returns mapping from date to (staffing_dict, source_rule) for every date in range."""
        result = {}
        curr = start_date
        while curr <= end_date:
            result[curr] = self.get_effective_staffing(curr)
            curr += timedelta(days=1)
        return result

    def add_day_range_rule(
        self,
        name: str,
        start_weekday: int,
        end_weekday: int,
        shift_mins: Dict[str, int],
    ) -> DayRangeRule:
        rule_id = f"rule_{len(self.day_range_rules) + 1}"
        rule = DayRangeRule(
            rule_id=rule_id,
            name=name,
            start_weekday=start_weekday,
            end_weekday=end_weekday,
            shift_mins=shift_mins,
            active=True,
        )
        self.day_range_rules.append(rule)
        return rule

    def remove_day_range_rule(self, rule_id: str) -> bool:
        initial_len = len(self.day_range_rules)
        self.day_range_rules = [r for r in self.day_range_rules if r.rule_id != rule_id]
        return len(self.day_range_rules) < initial_len

    def set_date_override(self, target_date: date, shift_mins: Dict[str, int], reason: str = ""):
        self.date_overrides[target_date] = DateOverrideRule(
            date=target_date, shift_mins=shift_mins, reason=reason
        )

    def remove_date_override(self, target_date: date):
        if target_date in self.date_overrides:
            del self.date_overrides[target_date]

    def update_shift_timing(
        self, code: str, start_time: time, end_time: time, crosses_midnight: bool
    ):
        if code in self.shifts:
            self.shifts[code].start_time = start_time
            self.shifts[code].end_time = end_time
            self.shifts[code].crosses_midnight = crosses_midnight
            # Recalculate duration
            d = date(2026, 1, 1)
            st = datetime.combine(d, start_time)
            et_d = d + timedelta(days=1) if crosses_midnight else d
            et = datetime.combine(et_d, end_time)
            self.shifts[code].duration_hours = (et - st).total_seconds() / 3600.0
