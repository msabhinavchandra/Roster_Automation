# Context Restoration Document: Enterprise Roster Automation System

## 1. Project Overview & Mission

This project is a standalone, mathematically exact, algorithmic employee roster automation system for 24/7 production support and release support.
It is built with:
- **Backend:** Python 3.11+, Google OR-Tools CP-SAT constraint optimization engine, pandas, openpyxl.
- **Frontend:** Streamlit multi-page interface.
- **Auditing:** Centralized authoritative validation pipeline enforcing zero-tolerance compliance.
- **Zero AI runtime dependencies:** No LLMs, OpenAI, or external heuristics. All scheduling choices derive from mathematical constraint satisfaction and multi-objective optimization.

---

## 2. Current Implementation Status

All mandatory modules, Streamlit UI screens, automated tests, deployment artifacts, sample data, and handover documents are fully implemented and verified:
- [x] Data models & dataclasses (`src/models.py`)
- [x] Configuration & 5-tier rule precedence engine (`src/configuration.py`)
- [x] Immediate mathematical capacity prechecks (`src/feasibility.py`)
- [x] Google OR-Tools CP-SAT constraint model (`src/constraints.py`)
- [x] Multi-mode scheduling engine (`src/scheduler.py`)
- [x] Authoritative centralized validation pipeline (`src/validation.py`)
- [x] Multi-tab Excel import/export & styling (`src/excel_handler.py`)
- [x] Historical analysis & phase continuity inference (`src/historical_analysis.py`)
- [x] Streamlit multi-page application (`app.py`, `pages/1_Overview.py` to `pages/8_Historical_Analysis.py`)
- [x] Pytest automated test suite (`tests/`) covering all 24 required test scenarios
- [x] Dockerfile, .dockerignore, Kubernetes deployment & service manifests
- [x] Handover documentation (`docs/`)

---

## 3. Directory Layout

```text
D:\DBS\Roster_Automation\
├── app.py                           # Streamlit entry point
├── requirements.txt                 # Dependencies
├── README.md                        # Project documentation
├── Dockerfile                       # Production container build
├── .dockerignore                    # Container build exclusions
├── .gitignore                       # Git exclusions
├── src/
│   ├── __init__.py
│   ├── models.py                    # Core domain entities & Enums
│   ├── configuration.py             # Staffing matrix & rule precedence
│   ├── feasibility.py               # Analytical prechecks & math bounds
│   ├── constraints.py               # OR-Tools CP-SAT mathematical formulations
│   ├── scheduler.py                 # Multi-mode CP-SAT solver runner
│   ├── validation.py                # Authoritative centralized validation
│   ├── excel_handler.py             # Excel import/export, styling, templates
│   ├── historical_analysis.py       # Past compliance audit & cycle phase inference
│   └── state.py                     # Streamlit session state initializer
├── pages/
│   ├── 1_Overview.py                # System status & KPI dashboard
│   ├── 2_Employees.py               # Employee management & workbook upload
│   ├── 3_Staffing_Rules.py          # Matrix & day-range rule editor
│   ├── 4_Holidays_and_Leave.py      # Holidays, custom policies, leave dates
│   ├── 5_Generate_Roster.py         # Generation runner & diagnostic panel
│   ├── 6_Review_and_Publish.py      # Interactive grid review, edit & publish
│   ├── 7_Night_Shift_Dashboard.py   # Circadian fatigue monitor & 10-cap chart
│   └── 8_Historical_Analysis.py     # Historical roster parser & phase adoption
├── tests/
│   ├── conftest.py                  # Pytest fixtures
│   ├── test_models_and_config.py    # Shift timing, rest, precedence tests
│   ├── test_excel_workflow.py       # Import/export, sheet preservation tests
│   ├── test_feasibility.py          # Math prechecks, infeasibility, timeouts
│   ├── test_validation.py           # 5/2 cycles, caps, leaves, publication block
│   └── test_scheduler_and_modes.py  # End-to-end Mode B & C generation
├── data/
│   ├── sample_employees.xlsx        # 50 employees sample workbook
│   └── sample_holidays.xlsx         # Sample public holidays workbook
├── output/
│   ├── .gitkeep
│   └── roster_generated.xlsx        # Default exported roster workbook
├── deployment/
│   ├── kubernetes-deployment.yaml   # K8s Deployment manifest
│   └── kubernetes-service.yaml      # K8s Service and PVC manifest
└── docs/
    ├── ALGORITHM_EXPLANATION.md     # In-depth OR-Tools explanation & tutorial
    ├── DEPLOYMENT_GUIDE.md          # Local, VM, Docker, Kubernetes instructions
    ├── ROSTER_AUTOMATION_CONTEXT.md # This context restoration document
    └── IMPLEMENTATION_REPORT.md     # Final implementation audit & results
```

---

## 4. Key Rules & Parameters

### Shift Definitions
- **S1 (Morning):** 06:30 to 15:30 (Duration: 9.0h).
- **S2 (Evening):** 14:00 to 23:00 (Duration: 9.0h). Intentional 1.5h handover overlap with S1.
- **S3 (Night):** 22:00 to 07:00 next day (Duration: 9.0h, crosses midnight). Intentional 1.0h overlap with S2, 0.5h overlap with S1 next morning.
- **Shift Overlaps:** Employees cannot be assigned to overlapping shifts.

### Work / OFF Cycle
- Repeating **5 consecutive working days followed by 2 consecutive OFF days**.
- The 5 working days form a cohesive **shift block** (same shift throughout).
- The 2 OFF days must immediately follow the 5-day block.
- Cycle continuity must be preserved across month boundaries.

### Night Shift Health Policy (Zero-Tolerance)
- **Hard Monthly S3 Cap:** Maximum **10 S3 shifts** per employee per calendar month.
- **Block Cap:** Maximum **two 5-night blocks** per employee per calendar month.
- **Mandatory 2 OFF Days:** Following an S3 block, 2 consecutive OFF days are mandatory.
- **55 Hours Elapsed Rest:** S3 ending 07:00 Saturday + Saturday OFF + Sunday OFF + S2 starting 14:00 Monday yields 55.0 continuous hours of rest ($\ge 11.0$h minimum).

### Default Staffing Matrix (7 Days × 3 Shifts)
- **Sunday:** S1=2, S2=6, S3=6 (Total 14).
- **Monday:** S1=4, S2=10, S3=8 (Total 22).
- **Tuesday:** S1=4, S2=10, S3=8 (Total 22).
- **Wednesday through Saturday:** S1=6, S2=14, S3=16 (Total 36 each day).

### Rule Precedence Order
1. Date-specific staffing overrides (Highest)
2. Applied holiday policy (Sunday / Custom / Normal)
3. Explicit individual-weekday rules
4. Applicable weekday-range rules
5. Base default staffing matrix (Lowest)

---

## 5. How to Run, Test, and Operate

### Run the Application
```bash
cd D:\DBS\Roster_Automation
streamlit run app.py
```

### Run Tests
```bash
python -m pytest -v
```

### Key Modules and Entry Functions
- `src/feasibility.py:run_feasibility_precheck(config, employees, start_d, end_d)`
- `src/scheduler.py:RosterScheduler.generate(employees, start_d, end_d, mode, time_limit_seconds)`
- `src/validation.py:validate_roster(schedule, config, employees)`
- `src/excel_handler.py:export_roster_to_excel(...)`
- `src/historical_analysis.py:parse_and_analyze_historical_roster(...)`
