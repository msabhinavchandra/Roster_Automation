"""Scheduler Engine utilizing Google OR-Tools CP-SAT.
Coordinates feasibility analysis, model building, solver execution,
result extraction, and validation for Mode A, Mode B, and Mode C.
"""

from __future__ import annotations
import time
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple, Any
from ortools.sat.python import cp_model

from src.models import (
    Employee,
    RosterSchedule,
    SchedulingMode,
    ValidationReport,
    ValidationStatus,
    FeasibilityStatus,
)
from src.configuration import RosterConfig
from src.feasibility import run_feasibility_precheck
from src.constraints import RosterConstraintBuilder
from src.validation import validate_roster


class RosterScheduler:
    def __init__(self, config: RosterConfig):
        self.config = config

    def generate(
        self,
        employees: List[Employee],
        start_date: date,
        end_date: date,
        mode: Optional[SchedulingMode] = None,
        time_limit_seconds: Optional[int] = None,
    ) -> Tuple[Optional[RosterSchedule], ValidationReport, str]:
        """Main entry point to generate an automated employee roster.
        Executes prechecks, builds CP-SAT model, solves, and performs full authoritative validation.

        Returns: (schedule_or_none, validation_report, status_message)
        """
        chosen_mode = mode or self.config.mode
        limit_sec = time_limit_seconds or self.config.solver_time_limit_seconds

        # 1. Immediate Feasibility Precheck
        precheck = run_feasibility_precheck(self.config, employees, start_date, end_date)
        if precheck.status == FeasibilityStatus.INFEASIBLE:
            report = ValidationReport(
                status=ValidationStatus.INFEASIBLE,
                metrics={"precheck_report": precheck},
            )
            explanation = "\n".join(precheck.messages)
            return None, report, f"Feasibility precheck failed: {explanation}"

        # 2. Build Date Range
        dates = []
        curr = start_date
        while curr <= end_date:
            dates.append(curr)
            curr += timedelta(days=1)

        # 3. Build CP-SAT Model
        builder = RosterConstraintBuilder(
            config=self.config,
            employees=employees,
            dates=dates,
            mode=chosen_mode,
        )
        model = builder.build_model()

        # 4. Configure Solver
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = float(limit_sec)
        solver.parameters.random_seed = self.config.random_seed
        solver.parameters.num_search_workers = 4

        start_time = time.time()
        solve_status = solver.Solve(model)
        solve_duration = time.time() - start_time
        status_name = solver.StatusName(solve_status)

        # 5. Evaluate Solver Outcome
        if solve_status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            # Extract assignments
            schedule = RosterSchedule(
                start_date=start_date,
                end_date=end_date,
                employees=employees,
                mode=chosen_mode,
                solver_status=status_name,
                solve_time_seconds=round(solve_duration, 2),
                is_published=False,
            )

            for e in employees:
                emp_id = e.id
                for d_idx, d in enumerate(dates):
                    assigned_shift = "OFF"
                    for s in ["S1", "S2", "S3", "OFF"]:
                        if (emp_id, d_idx, s) in builder.x:
                            if solver.Value(builder.x[emp_id, d_idx, s]) == 1:
                                assigned_shift = s
                                break
                    schedule.set_assignment(emp_id, d, assigned_shift)

            # 6. Centralized Authoritative Validation
            val_report = validate_roster(schedule, self.config, employees)
            schedule.validation_report = val_report

            status_msg = (
                f"Roster generated successfully in {solve_duration:.2f}s "
                f"(Solver: {status_name}, Status: {val_report.status.value})."
            )
            return schedule, val_report, status_msg

        elif solve_status == cp_model.INFEASIBLE:
            report = ValidationReport(
                status=ValidationStatus.INFEASIBLE,
                metrics={"solve_time": solve_duration},
            )
            diag_msg = (
                f"CP-SAT proved that no valid schedule exists (Model is INFEASIBLE) under the requested constraints "
                f"for {chosen_mode.value}. "
            )
            if chosen_mode == SchedulingMode.MODE_A:
                diag_msg += (
                    "Reason: Strict rotation (S1->S2->S3->S2->S1) enforces symmetric shift participation "
                    "which cannot satisfy the asymmetric weekly shift demands (S1=34, S2=82, S3=86) "
                    "within available headcount capacity. Recommendation: Switch to Mode B (Health-First, Coverage-Oriented)."
                )
            else:
                diag_msg += (
                    "Possible conflicting rules include 5-on/2-off cycle constraints, peak daily coverage minimums, "
                    "or monthly night-shift caps. Try adjusting minimum staffing or increasing the employee pool."
                )
            return None, report, diag_msg

        else:  # UNKNOWN or MODEL_INVALID (e.g. timeout)
            report = ValidationReport(
                status=ValidationStatus.UNRESOLVED,
                metrics={"solve_time": solve_duration},
            )
            msg = (
                f"Solver timed out after {solve_duration:.1f}s without establishing feasibility. "
                f"Status: UNRESOLVED. Try increasing the solver time limit or simplifying rules."
            )
            return None, report, msg
