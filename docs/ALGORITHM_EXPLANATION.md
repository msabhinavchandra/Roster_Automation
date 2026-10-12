# Algorithm Explanation & Operations Research Guide: Roster Automation System

Welcome! This document explains how the **Enterprise Roster Automation System** designs fair, mathematically optimal schedules for 24/7 production and release support.

Every section starts with a **Beginner-Friendly Explanation** (using plain language analogies) followed immediately by a **Technical Deep-Dive** (for senior engineers and mathematical optimization specialists).

---

## 1. System Architecture

### 🟢 Beginner-Friendly Explanation
Imagine organizing a large puzzle with 50 people across 30 days. Each person needs specific work days and rest days, and each shift needs a guaranteed minimum number of engineers. Instead of trying to guess combinations by hand in Excel or using random trial-and-error, our system operates like an automated puzzle master:
1. **The Inspector (Feasibility Precheck):** Checks if the puzzle is even theoretically possible before wasting any time.
2. **The Architect (Constraint Builder):** Translates every human rule (e.g. "5 days work then 2 days rest", "max 10 nights a month") into strict mathematical equations.
3. **The Solver (Google OR-Tools CP-SAT):** Evaluates millions of potential combinations in seconds to find an optimal solution.
4. **The Auditor (Centralized Validator):** Independently checks every single day, employee, and shift in the final schedule to guarantee zero errors before anyone can publish it.

### 🔷 Technical Deep-Dive
The architecture follows a clean hexagonal/layered design:
- **Domain Entities (`src/models.py`):** Pure immutable dataclasses and enums (`Employee`, `ShiftDefinition`, `Holiday`, `RosterSchedule`, `ValidationReport`).
- **Configuration & Precedence (`src/configuration.py`):** Evaluates hierarchical precedence: `Date Override > Holiday Policy > Individual Weekday Rule > Day-Range Rule > Base Matrix`.
- **Precheck Engine (`src/feasibility.py`):** $O(N)$ analytical bounds checker verifying aggregate worker-days and pigeonhole bounds.
- **Optimization Model (`src/constraints.py`):** Formulates integer programming / boolean satisfiability constraints for Google OR-Tools CP-SAT.
- **Solving Engine (`src/scheduler.py`):** Orchestrates solver parameters (multi-threaded branch-and-bound, time limits, deterministic seeds).
- **Authoritative Validator (`src/validation.py`):** Single source of truth for compliance auditing.

---

## 2. Decision Variables

### 🟢 Beginner-Friendly Explanation
Think of a decision variable like a light switch for every employee, on every date, for every shift.
- Switch $X(\text{Alice}, \text{Nov 5}, \text{S1}) = 1$ means Alice works Morning Shift (S1) on November 5.
- Switch $X(\text{Alice}, \text{Nov 5}, \text{OFF}) = 1$ means Alice takes a scheduled day off on November 5.

### 🔷 Technical Deep-Dive
The CP-SAT model defines two core variable sets:
1. **Assignment Variables ($x_{e, d, s} \in \{0, 1\}$):**
   - For each employee $e \in E$, date index $d \in \{0, \dots, D-1\}$, and shift $s \in \{\text{S1}, \text{S2}, \text{S3}, \text{OFF}\}$.
   - **Exclusivity Constraint:**
     $$\sum_{s \in \{\text{S1}, \text{S2}, \text{S3}, \text{OFF}\}} x_{e, d, s} = 1 \quad \forall e \in E, \forall d$$

2. **Cycle Phase Variables ($y_{e, p} \in \{0, 1\}$):**
   - For each employee $e$ and phase offset $p \in \{0, 1, 2, 3, 4, 5, 6\}$.
   - Phase $p$ dictates the start of the 7-day repeating (5-work / 2-off) cycle.
   - **Phase Exclusivity:**
     $$\sum_{p=0}^{6} y_{e, p} = 1 \quad \forall e \in E_{active}$$

---

## 3. The 5-on / 2-off Cycle & Shift-Block Continuity

### 🟢 Beginner-Friendly Explanation
Every employee follows a healthy, predictable human rhythm: work 5 days in a row, then take exactly 2 days off. This 7-day pattern repeats continuously.
Crucially, during those 5 working days (a "shift block"), the employee stays on the **exact same shift** (e.g. 5 days of S1, or 5 days of S3). They never hop randomly from morning to night from one day to the next.

### 🔷 Technical Deep-Dive
Let $t = d$ be the day index from roster start date. For an employee in phase $p$, the cycle day is $c(d, p) = (d - p) \pmod 7$.
- If $c(d, p) \in \{5, 6\}$, day $d$ is an OFF day:
  $$y_{e, p} = 1 \implies x_{e, d, \text{OFF}} = 1$$
- If $c(d, p) \in \{0, 1, 2, 3, 4\}$, day $d$ is a WORKING day:
  $$y_{e, p} = 1 \implies x_{e, d, \text{OFF}} = 0$$
- **Shift-Block Uniformity:** Within each 5-day block (where $c(d, p) < 4$ and $c(d+1, p) = c(d, p) + 1$):
  $$y_{e, p} = 1 \implies x_{e, d, s} = x_{e, d+1, s} \quad \forall s \in \{\text{S1}, \text{S2}, \text{S3}\}$$

---

## 4. Night-Shift Circadian Health Policy

### 🟢 Beginner-Friendly Explanation
Working at night is physically taxing. To protect employee wellbeing, our engine enforces unbreakable biological safety rules:
1. **Monthly Night Cap:** No employee may work more than **10 S3 shifts in a calendar month**.
2. **Night Blocks:** An S3 assignment comes in a structured 5-night block. Therefore, an employee can do at most two 5-night blocks in a month.
3. **Mandatory Post-Night Rest:** Immediately after completing a 5-night block, the employee receives **2 consecutive OFF days**. Because S3 finishes at 07:00 Saturday morning, taking Saturday and Sunday off provides **55 hours of unbroken rest** before starting an afternoon shift on Monday at 14:00!

### 🔷 Technical Deep-Dive
For each calendar month $M = (year, month)$:
Let $D_M$ be the indices of all dates falling within calendar month $M$.
$$\sum_{d \in D_M} x_{e, d, \text{S3}} \le 10 \quad \forall e \in E$$
Because the 5-on/2-off cycle enforces that every 5 working days are followed by 2 OFF days, any 5-day S3 block is inherently followed by 2 consecutive OFF days.
Elapsed rest hours $R$ between S3 end (07:00 day $d$) and S2 start (14:00 day $d+2$):
$$R = (24 - 7) + 24 + 14 = 55.0 \text{ hours} \ge 11.0 \text{ hours}$$

---

## 5. Daily Staffing Coverage & Objective Function

### 🟢 Beginner-Friendly Explanation
On every calendar day, each shift has a minimum headcount requirement (e.g. Wednesday S3 needs at least 16 people). The solver ensures every shift meets or exceeds this floor, while gently steering the system towards fairness, balanced night shifts, and minimal unnecessary staffing.

### 🔷 Technical Deep-Dive
**Hard Minimum Coverage:**
For every date $d$ and shift $s \in \{\text{S1}, \text{S2}, \text{S3}\}$ with required minimum $R_{d, s}$:
$$\sum_{e \in E_{active}} x_{e, d, s} \ge R_{d, s}$$

**Multi-Objective Function:**
The solver minimizes a weighted sum of operational deviations:
$$\min \left( W_{\text{excess}} \sum_{d, s} \text{Excess}_{d, s} + W_{\text{night}} \cdot \text{MaxS3} + W_{\text{weekend}} \cdot \text{MaxWeekend} + W_{\text{rot}} \sum \text{Deviation} \right)$$
Where:
- $\text{Excess}_{d, s} = \sum_{e} x_{e, d, s} - R_{d, s} \ge 0$.
- $\text{MaxS3} \ge \sum_{d} x_{e, d, \text{S3}} \quad \forall e$ (enforcing min-max equity).
- Weights are transparently configured in `HeadcountPreferences`.

---

## 6. How to Add a New Constraint or Staffing Rule

### Beginner Guide
To add a new operational rule (for example, "No employee works S3 if they have less than 6 months experience"):
1. Add an attribute (e.g. `experience_months: int`) to `Employee` in `src/models.py`.
2. Open `src/constraints.py`.
3. In `add_night_shift_constraints`, write:
   ```python
   if employee.experience_months < 6:
       for d_idx in range(self.num_days):
           self.model.Add(self.x[employee.id, d_idx, "S3"] == 0)
   ```
4. Add the corresponding verification check in `src/validation.py` to ensure manual edits in the UI also respect this rule.
5. Run `pytest` to verify!
