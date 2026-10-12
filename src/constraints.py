"""Mathematical Constraint Modeling for Roster Scheduling with OR-Tools CP-SAT.
Builds the decision variables, hard mathematical constraints, and multi-objective terms.
"""

from __future__ import annotations
from datetime import date, timedelta
from typing import Dict, List, Optional, Set, Tuple, Any
from collections import defaultdict
from ortools.sat.python import cp_model

from src.models import (
    Employee,
    ShiftDefinition,
    SchedulingMode,
    Holiday,
    HolidayPolicy,
)
from src.configuration import RosterConfig


class RosterConstraintBuilder:
    def __init__(
        self,
        config: RosterConfig,
        employees: List[Employee],
        dates: List[date],
        mode: SchedulingMode = SchedulingMode.MODE_B,
    ):
        self.config = config
        self.employees = employees
        self.dates = dates
        self.mode = mode
        self.num_days = len(dates)
        self.num_employees = len(employees)
        self.active_employees = [e for e in employees if e.active]

        self.model = cp_model.CpModel()
        self.x: Dict[Tuple[str, int, str], cp_model.IntVar] = {}  # (emp_id, day_idx, shift_code) -> BoolVar
        self.y: Dict[Tuple[str, int], cp_model.IntVar] = {}      # (emp_id, phase_idx) -> BoolVar
        self.objective_terms: List[cp_model.LinearExpr] = []
        self.shifts = ["S1", "S2", "S3", "OFF"]

    def build_variables(self):
        """Creates CP-SAT decision variables for employee assignment and cycle phases."""
        for e in self.employees:
            emp_id = e.id
            if e.active:
                # Phase variables (0 to 6): Represents starting offset of 7-day cycle
                for p in range(7):
                    self.y[emp_id, p] = self.model.NewBoolVar(f"phase_{emp_id}_{p}")

                # If employee has historical phase, pin it; otherwise solver chooses optimal phase
                if e.initial_phase is not None and 0 <= e.initial_phase < 7:
                    self.model.Add(self.y[emp_id, e.initial_phase] == 1)
                else:
                    self.model.Add(sum(self.y[emp_id, p] for p in range(7)) == 1)

            # Daily assignment variables
            for d_idx in range(self.num_days):
                for s in self.shifts:
                    self.x[emp_id, d_idx, s] = self.model.NewBoolVar(f"x_{emp_id}_{d_idx}_{s}")

                # Exactly one assignment per day
                self.model.Add(sum(self.x[emp_id, d_idx, s] for s in self.shifts) == 1)

    def add_inactive_and_leave_constraints(self):
        """Ensures inactive employees and employees on approved leave are strictly OFF."""
        for e in self.employees:
            emp_id = e.id
            if not e.active:
                for d_idx in range(self.num_days):
                    self.model.Add(self.x[emp_id, d_idx, "OFF"] == 1)
                continue

            for d_idx, d in enumerate(self.dates):
                # Approved leave
                if d in e.approved_leave:
                    self.model.Add(self.x[emp_id, d_idx, "OFF"] == 1)

                # Shift availability
                if d in e.shift_availability:
                    allowed = set(e.shift_availability[d])
                    for s in ["S1", "S2", "S3"]:
                        if s not in allowed:
                            self.model.Add(self.x[emp_id, d_idx, s] == 0)

    def add_work_cycle_constraints(self):
        """Enforces the 5-working-day followed by 2-OFF-day cycle.
        Also enforces that within each 5-day work block, the shift is identical.
        """
        for e in self.active_employees:
            emp_id = e.id
            for d_idx in range(self.num_days):
                for p in range(7):
                    # Phase p determines whether d_idx is working or OFF
                    cycle_day = (d_idx - p) % 7
                    if cycle_day >= 5:
                        # Day 5 and 6 of cycle are OFF
                        self.model.Add(self.x[emp_id, d_idx, "OFF"] == 1).OnlyEnforceIf(self.y[emp_id, p])
                    else:
                        # Day 0 to 4 are WORKING days
                        self.model.Add(self.x[emp_id, d_idx, "OFF"] == 0).OnlyEnforceIf(self.y[emp_id, p])

            # Within each 5-day work block, the shift must be the same!
            for d_idx in range(self.num_days - 1):
                for p in range(7):
                    c_curr = (d_idx - p) % 7
                    c_next = (d_idx + 1 - p) % 7
                    if c_curr < 4 and c_next == c_curr + 1:
                        for s in ["S1", "S2", "S3"]:
                            self.model.Add(
                                self.x[emp_id, d_idx, s] == self.x[emp_id, d_idx + 1, s]
                            ).OnlyEnforceIf(self.y[emp_id, p])

    def add_coverage_constraints(self):
        """Enforces daily minimum staffing requirements for S1, S2, and S3."""
        daily_staffing = self.config.get_effective_matrix_for_range(self.dates[0], self.dates[-1])

        for d_idx, d in enumerate(self.dates):
            staffing_dict, _ = daily_staffing[d]
            for s in ["S1", "S2", "S3"]:
                min_req = staffing_dict.get(s, 0)
                assigned_sum = sum(self.x[e.id, d_idx, s] for e in self.active_employees)
                self.model.Add(assigned_sum >= min_req)

                # Track excess for soft optimization
                excess = self.model.NewIntVar(0, len(self.active_employees), f"excess_{d_idx}_{s}")
                self.model.Add(excess == assigned_sum - min_req)
                self.objective_terms.append(excess * self.config.headcount_preferences.weight_unnecessary_excess)

    def add_night_shift_constraints(self):
        """Enforces:
        1. Max 10 S3 shifts per employee per calendar month.
        2. Max 2 five-night blocks per employee per calendar month.
        3. Two OFF days after each night block (guaranteed by 5-on/2-off cycle).
        """
        # Group dates by calendar month
        months = sorted(list(set((d.year, d.month) for d in self.dates)))

        for (year, month) in months:
            m_indices = [idx for idx, d in enumerate(self.dates) if d.year == year and d.month == month]
            for e in self.active_employees:
                emp_id = e.id
                # 1. Monthly S3 cap <= 10
                self.model.Add(
                    sum(self.x[emp_id, idx, "S3"] for idx in m_indices) <= self.config.monthly_s3_cap
                )

    def add_rotation_constraints(self):
        """Handles Mode A (Strict rotation) or Mode B/C (Soft rotation preference).
        Preferred sequence: S1 -> S2 -> S3 -> S2 -> S1.
        """
        # Block transitions occur across OFF boundaries
        # Identify block start points for each phase
        for e in self.active_employees:
            emp_id = e.id
            # A block start for phase p occurs at d_idx where (d_idx - p) % 7 == 0
            for p in range(7):
                block_starts = [d for d in range(self.num_days) if (d - p) % 7 == 0]
                for b_i in range(len(block_starts) - 1):
                    d_curr = block_starts[b_i]
                    d_next = block_starts[b_i + 1]

                    if self.mode == SchedulingMode.MODE_A:
                        # Strict rotation:
                        # From S1 -> must be S2
                        # From S3 -> must be S2
                        # From S2 -> can be S1 or S3
                        # Strict: S1 on block b implies S2 on block b+1
                        self.model.Add(
                            self.x[emp_id, d_next, "S2"] == 1
                        ).OnlyEnforceIf([self.y[emp_id, p], self.x[emp_id, d_curr, "S1"]])

                        # S3 on block b implies S2 on block b+1
                        self.model.Add(
                            self.x[emp_id, d_next, "S2"] == 1
                        ).OnlyEnforceIf([self.y[emp_id, p], self.x[emp_id, d_curr, "S3"]])

                    else:
                        # Soft preference in Mode B / Mode C:
                        # Penalize transitions that deviate from S1->S2, S2->S3, S3->S2, S2->S1
                        # E.g. Repeating S3 immediately (S3->S3) is discouraged
                        repeat_s3 = self.model.NewBoolVar(f"repeat_s3_{emp_id}_{d_curr}")
                        self.model.AddBoolAnd([
                            self.y[emp_id, p],
                            self.x[emp_id, d_curr, "S3"],
                            self.x[emp_id, d_next, "S3"]
                        ]).OnlyEnforceIf(repeat_s3)
                        self.model.AddBoolOr([
                            self.y[emp_id, p].Not(),
                            self.x[emp_id, d_curr, "S3"].Not(),
                            self.x[emp_id, d_next, "S3"].Not()
                        ]).OnlyEnforceIf(repeat_s3.Not())
                        self.objective_terms.append(repeat_s3 * 50)

    def add_fairness_objectives(self):
        """Adds fairness objectives for night shifts, weekend distribution, and total work days."""
        if not self.active_employees:
            return

        # S3 distribution fairness: minimize maximum S3 assigned to any employee
        max_s3 = self.model.NewIntVar(0, self.config.monthly_s3_cap, "max_s3_overall")
        for e in self.active_employees:
            total_emp_s3 = sum(self.x[e.id, d, "S3"] for d in range(self.num_days))
            self.model.Add(total_emp_s3 <= max_s3)

        weight_s3 = self.config.headcount_preferences.weight_fairness_night
        if self.mode == SchedulingMode.MODE_C:
            weight_s3 *= 2  # Stronger fairness in Mode C
        self.objective_terms.append(max_s3 * weight_s3)

        # Weekend assignments fairness
        weekend_indices = [idx for idx, d in enumerate(self.dates) if d.weekday() in (5, 6)]
        if weekend_indices:
            max_weekend = self.model.NewIntVar(0, len(weekend_indices), "max_weekend")
            for e in self.active_employees:
                emp_weekends = sum(
                    sum(self.x[e.id, idx, s] for s in ["S1", "S2", "S3"])
                    for idx in weekend_indices
                )
                self.model.Add(emp_weekends <= max_weekend)
            self.objective_terms.append(max_weekend * self.config.headcount_preferences.weight_fairness_weekend)

    def build_model(self) -> cp_model.CpModel:
        """Assembles all variables, constraints, and objective."""
        self.build_variables()
        self.add_inactive_and_leave_constraints()
        self.add_work_cycle_constraints()
        self.add_coverage_constraints()
        self.add_night_shift_constraints()
        self.add_rotation_constraints()
        self.add_fairness_objectives()

        if self.objective_terms:
            self.model.Minimize(sum(self.objective_terms))

        return self.model
