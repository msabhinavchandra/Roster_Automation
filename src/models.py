"""Domain models for the Roster Automation System.
Includes shifts, employees, rules, holidays, assignments, and validation structures.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple, Any


class ShiftCode(str, Enum):
    S1 = "S1"
    S2 = "S2"
    S3 = "S3"
    OFF = "OFF"


class SchedulingMode(str, Enum):
    MODE_A = "MODE_A"  # Strict preferred rotation (S1 -> S2 -> S3 -> S2 -> S1)
    MODE_B = "MODE_B"  # Health-first, coverage-oriented (Default)
    MODE_C = "MODE_C"  # Fairness-optimized rotation


class HolidayPolicy(str, Enum):
    NORMAL = "NORMAL"      # Keep weekday staffing
    SUNDAY = "SUNDAY"      # Apply Sunday staffing
    CUSTOM = "CUSTOM"      # Custom staffing matrix


class ValidationStatus(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    INFEASIBLE = "INFEASIBLE"
    UNRESOLVED = "UNRESOLVED"


class FeasibilityStatus(str, Enum):
    FEASIBLE_BY_PRECHECK = "FEASIBLE BY PRECHECK"
    INFEASIBLE = "INFEASIBLE"
    UNRESOLVED = "UNRESOLVED"


@dataclass
class ShiftDefinition:
    code: str
    name: str
    start_time: time
    end_time: time
    crosses_midnight: bool = False
    duration_hours: float = 9.0

    def start_datetime(self, d: date) -> datetime:
        """Returns the start datetime of this shift on calendar date d."""
        return datetime.combine(d, self.start_time)

    def end_datetime(self, d: date) -> datetime:
        """Returns the end datetime of this shift starting on date d.
        If crosses_midnight is True, the end datetime is on d + 1 day.
        """
        end_d = d + timedelta(days=1) if self.crosses_midnight else d
        return datetime.combine(end_d, self.end_time)


DEFAULT_SHIFTS: Dict[str, ShiftDefinition] = {
    "S1": ShiftDefinition(
        code="S1",
        name="Morning Shift",
        start_time=time(6, 30),
        end_time=time(15, 30),
        crosses_midnight=False,
        duration_hours=9.0,
    ),
    "S2": ShiftDefinition(
        code="S2",
        name="Afternoon/Evening Shift",
        start_time=time(14, 0),
        end_time=time(23, 0),
        crosses_midnight=False,
        duration_hours=9.0,
    ),
    "S3": ShiftDefinition(
        code="S3",
        name="Night Shift",
        start_time=time(22, 0),
        end_time=time(7, 0),
        crosses_midnight=True,
        duration_hours=9.0,
    ),
}


def calculate_rest_hours(
    prev_date: date,
    prev_shift: str,
    next_date: date,
    next_shift: str,
    shifts: Dict[str, ShiftDefinition] = DEFAULT_SHIFTS,
) -> float:
    """Calculates exact elapsed rest hours between the end of prev_shift and the start of next_shift.
    If either shift is OFF, returns infinite/maximum float or rest across intermediate days.
    """
    if prev_shift == "OFF" or next_shift == "OFF":
        return 999.0

    if prev_shift not in shifts or next_shift not in shifts:
        return 999.0

    prev_end = shifts[prev_shift].end_datetime(prev_date)
    next_start = shifts[next_shift].start_datetime(next_date)
    delta = next_start - prev_end
    return delta.total_seconds() / 3600.0


@dataclass
class Employee:
    id: str
    name: str
    active: bool = True
    approved_leave: Set[date] = field(default_factory=set)
    shift_availability: Dict[date, List[str]] = field(default_factory=dict)
    initial_phase: Optional[int] = None  # 0 to 6 phase in 5-on/2-off cycle
    initial_last_shift: Optional[str] = None  # S1, S2, S3 before roster start
    extra_attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DayRangeRule:
    rule_id: str
    name: str
    start_weekday: int  # 0=Monday, 6=Sunday
    end_weekday: int    # 0=Monday, 6=Sunday
    shift_mins: Dict[str, int] = field(default_factory=dict)
    active: bool = True

    def matches_weekday(self, weekday: int) -> bool:
        """Checks if weekday (0=Mon..6=Sun) is contained in [start_weekday, end_weekday].
        Supports ranges crossing Sunday boundary (e.g. Fri(4) to Mon(0)).
        """
        if self.start_weekday <= self.end_weekday:
            return self.start_weekday <= weekday <= self.end_weekday
        else:
            return weekday >= self.start_weekday or weekday <= self.end_weekday


@dataclass
class DateOverrideRule:
    date: date
    shift_mins: Dict[str, int]
    reason: str = ""


@dataclass
class Holiday:
    date: date
    name: str
    description: str = ""
    policy: HolidayPolicy = HolidayPolicy.NORMAL
    custom_shift_mins: Dict[str, int] = field(default_factory=dict)


@dataclass
class ValidationIssue:
    severity: str  # "ERROR", "WARNING", "INFO"
    rule_name: str
    message: str
    employee_id: Optional[str] = None
    date: Optional[date] = None
    shift: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationReport:
    status: ValidationStatus
    issues: List[ValidationIssue] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        return self.status == ValidationStatus.VALID or (
            not any(i.severity == "ERROR" for i in self.issues)
            and self.status != ValidationStatus.INVALID
        )

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "ERROR")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "WARNING")


@dataclass
class FeasibilityReport:
    status: FeasibilityStatus
    messages: List[str] = field(default_factory=list)
    shortages: List[Dict[str, Any]] = field(default_factory=list)
    capacity_metrics: Dict[str, Any] = field(default_factory=dict)
    suggestions: List[str] = field(default_factory=list)

    @property
    def is_feasible(self) -> bool:
        return self.status == FeasibilityStatus.FEASIBLE_BY_PRECHECK


@dataclass
class RosterSchedule:
    start_date: date
    end_date: date
    assignments: Dict[Tuple[str, date], str] = field(default_factory=dict)
    employees: List[Employee] = field(default_factory=list)
    mode: SchedulingMode = SchedulingMode.MODE_B
    solver_status: str = "NOT_SOLVED"
    solve_time_seconds: float = 0.0
    is_published: bool = False
    created_at: datetime = field(default_factory=datetime.now)
    validation_report: Optional[ValidationReport] = None

    def get_assignment(self, emp_id: str, d: date) -> str:
        return self.assignments.get((emp_id, d), "OFF")

    def set_assignment(self, emp_id: str, d: date, shift: str):
        self.assignments[(emp_id, d)] = shift
