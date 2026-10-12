# Enterprise Employee Roster Automation System

An automated, mathematically optimal 24/7 production and release support rostering platform powered by **Google OR-Tools CP-SAT** and **Streamlit**.

---

## 🌟 Key Features

1. **24/7 Continuous Support Operations:**
   - Pre-configured shifts: S1 (06:30–15:30), S2 (14:00–23:00), S3 (22:00–07:00 next day).
   - Preserves operational shift handovers with intentional overlaps.
   - Rest calculations computed using exact timestamps.

2. **Strict Work/Rest & Circadian Health Policies:**
   - **5-Working-Day / 2-OFF-Day repeating cycle**: Maintains cycle continuity across months.
   - **Shift-Block Consistency**: Employee works the same shift during their 5-day block.
   - **Hard Monthly Night Cap**: Max 10 S3 shifts per employee per calendar month.
   - **Max Two 5-Night Blocks**: Max two S3 blocks per employee per calendar month.
   - **Post-Night Mandatory Rest**: 2 consecutive OFF days immediately following each S3 block (yielding 55 hours of continuous rest before resuming S2).

3. **Three Scheduling Modes:**
   - **Mode B (Default):** Health-first, coverage-oriented. Guarantees all hard constraints while satisfying demand.
   - **Mode A:** Strict preferred rotation (S1 → S2 → S3 → S2 → S1). Evaluates feasibility and diagnoses mathematical trade-offs.
   - **Mode C:** Fairness-optimized rotation. Optimizes night-shift distribution, weekend equity, and minimal excess staffing.

4. **Dynamic Staffing Rules & Rule Precedence:**
   - 7-day × 3-shift editable minimum staffing matrix.
   - Day-range rules (e.g. Wednesday through Saturday peak).
   - Date-specific overrides (highest precedence).
   - Clear deterministic precedence resolution.

5. **Immediate Feasibility Prechecks:**
   - Instant calculation of capacity bounds, rolling 7-day limits, and monthly night shift limits.
   - Real-time diagnostic alerts with calculated shortages and actionable suggestions.

6. **End-to-End Excel Workflow:**
   - Ingest employee workbooks (50+ staff) and holiday matrices.
   - Interactive schedule grid with manual shift adjustments and instant authoritative revalidation.
   - Publication-grade multi-sheet Excel export (Final Roster, Summary, Daily Coverage, Night Shift Summary, Validation, Feasibility, Applied Holidays).

7. **Fatigue & Continuity Dashboards:**
   - Night Shift Monitoring Dashboard with visual reference lines at 10 shifts.
   - Historical Roster Analyzer that infers cycle phases to ensure seamless continuity across roster cycles.

---

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Launch the Application
```bash
streamlit run app.py
```

### 3. Run Automated Tests
```bash
pytest -v
```

---

## 📁 Repository Structure

```text
roster-automation/
├── app.py                      # Main Streamlit entry hub
├── requirements.txt            # Python dependencies
├── Dockerfile                  # Containerization specification
├── .dockerignore
├── .gitignore
├── src/
│   ├── models.py               # Domain dataclasses & enums
│   ├── configuration.py        # Staffing rules & precedence engine
│   ├── scheduler.py            # CP-SAT scheduling engine
│   ├── constraints.py          # Mathematical CP-SAT formulations
│   ├── validation.py           # Authoritative centralized validation
│   ├── feasibility.py          # Instant capacity prechecks
│   ├── excel_handler.py        # openpyxl import/export & styling
│   ├── historical_analysis.py  # Historical auditing & phase inference
│   └── state.py                # Streamlit session state helper
├── pages/
│   ├── 1_Overview.py           # System status & metrics
│   ├── 2_Employees.py          # Employee pool & Excel upload
│   ├── 3_Staffing_Rules.py     # Staffing matrix & day-range rules
│   ├── 4_Holidays_and_Leave.py # Public holidays & employee leaves
│   ├── 5_Generate_Roster.py    # Mode selection & solver runner
│   ├── 6_Review_and_Publish.py # Grid review, edit & Excel download
│   ├── 7_Night_Shift_Dashboard.py # Circadian fatigue monitor
│   └── 8_Historical_Analysis.py# Historical audit & phase continuity
├── tests/                      # Pytest automated test suite
├── data/                       # Sample employee & holiday workbooks
├── output/                     # Server-side exported Excel rosters
├── docs/                       # Technical & handover documentation
└── deployment/                 # Kubernetes deployment & service manifests
```

---

## 📜 Documentation

- [Algorithm Explanation](docs/ALGORITHM_EXPLANATION.md)
- [Deployment Guide](docs/DEPLOYMENT_GUIDE.md)
- [Context Restoration Guide](docs/ROSTER_AUTOMATION_CONTEXT.md)
- [Implementation Report](docs/IMPLEMENTATION_REPORT.md)
