"""Pytest fixtures for Roster Automation test suite.
"""

import pytest
from datetime import date, time
from typing import List

from src.models import Employee, ShiftDefinition, DEFAULT_SHIFTS, SchedulingMode
from src.configuration import RosterConfig


@pytest.fixture
def sample_50_employees() -> List[Employee]:
    """Generates 50 active synthetic employees (EMP001 to EMP050)."""
    return [
        Employee(id=f"EMP{i:03d}", name=f"Employee {i}", active=True)
        for i in range(1, 51)
    ]


@pytest.fixture
def sample_20_employees() -> List[Employee]:
    """Generates 20 active synthetic employees."""
    return [
        Employee(id=f"EMP{i:03d}", name=f"Employee {i}", active=True)
        for i in range(1, 21)
    ]


@pytest.fixture
def default_config() -> RosterConfig:
    """Returns a fresh default RosterConfig."""
    return RosterConfig()


@pytest.fixture
def november_dates():
    """November 2026 dates (30 days, starting on Sunday)."""
    return date(2026, 11, 1), date(2026, 11, 30)
