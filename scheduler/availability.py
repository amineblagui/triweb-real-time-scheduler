"""Availability API interpretation and the notebook working calendar."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import pandas as pd

from .config import MAX_WEEKLY_HOURS, POST_TASK_BREAK_MINUTES, WORKING_PERIODS
from .employees import normalize_employee_id


class AvailabilityDataError(ValueError):
    """The availability payload cannot safely support a schedule."""


def prepare_availability(raw_availability: list[dict] | pd.DataFrame) -> pd.DataFrame:
    availability = pd.DataFrame(raw_availability).copy()
    required = {"userId", "workDateIso", "morningStatus", "afternoonStatus"}
    missing = sorted(required - set(availability.columns))
    if missing:
        raise AvailabilityDataError(f"Availability API is missing required scheduler fields: {', '.join(missing)}.")
    availability["EmployeeID"] = availability["userId"].map(normalize_employee_id)
    availability["Date"] = pd.to_datetime(availability["workDateIso"], errors="coerce").dt.normalize()
    availability["MorningStatus"] = availability["morningStatus"].astype(str).str.strip().str.casefold()
    availability["AfternoonStatus"] = availability["afternoonStatus"].astype(str).str.strip().str.casefold()
    availability["MorningAvailable"] = availability["MorningStatus"].eq("available")
    availability["AfternoonAvailable"] = availability["AfternoonStatus"].eq("available")
    availability = availability[availability["EmployeeID"].notna() & availability["Date"].notna()].copy()
    if availability.duplicated(["EmployeeID", "Date"]).any():
        raise AvailabilityDataError("Availability API contains duplicate employee/day records.")
    return availability.sort_values(["EmployeeID", "Date"]).reset_index(drop=True)


def clock(day: pd.Timestamp, hour: int, minute: int) -> pd.Timestamp:
    return pd.Timestamp(day).normalize() + pd.to_timedelta(f"{int(hour)}h {int(minute)}min")


def iso_week(moment: pd.Timestamp) -> int:
    return int(pd.Timestamp(moment).isocalendar().week)


def work_periods(day: pd.Timestamp) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    day = pd.Timestamp(day).normalize()
    if day.weekday() >= 5:
        return []
    return [(clock(day, start_hour, start_minute), clock(day, end_hour, end_minute)) for start_hour, start_minute, end_hour, end_minute in WORKING_PERIODS]


@dataclass
class AvailabilityCalendar:
    """Employee availability horizon with worker-safe calendar operations."""

    availability: pd.DataFrame
    active_employee_ids: set[str]

    def __post_init__(self) -> None:
        self._by_employee = {
            employee_id: group.set_index("Date").sort_index()
            for employee_id, group in self.availability.groupby("EmployeeID")
        }

    def daily(self, employee_id: object, day: pd.Timestamp) -> pd.Series | None:
        employee_id = normalize_employee_id(employee_id)
        if employee_id is None:
            return None
        employee_data = self._by_employee.get(employee_id)
        day = pd.Timestamp(day).normalize()
        if employee_data is None or day not in employee_data.index:
            return None
        return employee_data.loc[day]

    def physically_available(self, employee_id: object, instant: pd.Timestamp) -> bool:
        employee_id = normalize_employee_id(employee_id)
        if employee_id is None or employee_id not in self.active_employee_ids:
            return False
        instant = pd.Timestamp(instant)
        daily = self.daily(employee_id, instant)
        if daily is None:
            return False
        if clock(instant, 8, 30) <= instant < clock(instant, 12, 30):
            return bool(daily["MorningAvailable"])
        if clock(instant, 13, 30) <= instant < clock(instant, 17, 0):
            return bool(daily["AfternoonAvailable"])
        return False

    def horizon_end(self, employee_id: object) -> pd.Timestamp | None:
        employee_id = normalize_employee_id(employee_id)
        data = self._by_employee.get(employee_id) if employee_id else None
        if data is None or data.empty:
            return None
        return clock(data.index.max(), 17, 0)

    def next_work(self, employee_id: object, instant: pd.Timestamp) -> pd.Timestamp | None:
        """Next physically available moment, or None outside the API horizon."""
        employee_id = normalize_employee_id(employee_id)
        if employee_id is None:
            return None
        data = self._by_employee.get(employee_id)
        if data is None or data.empty:
            return None
        cursor = pd.Timestamp(instant)
        max_date = pd.Timestamp(data.index.max()).normalize()
        while cursor.normalize() <= max_date:
            for period_start, period_end in work_periods(cursor):
                if cursor >= period_end:
                    continue
                candidate = max(cursor, period_start)
                if self.physically_available(employee_id, candidate):
                    return candidate
            cursor = clock(cursor + pd.Timedelta("1D"), 8, 30)
        return None

    def task_schedule(
        self,
        employee_id: object,
        earliest: pd.Timestamp,
        duration_hours: float,
        weekly_allocations: dict[int, float] | None = None,
    ) -> tuple[bool, pd.Timestamp | None, pd.Timestamp | None, dict[int, float]]:
        """Fit a complete task in physical availability and the 38-hour week cap."""
        if duration_hours <= 0:
            raise ValueError("duration_hours must be greater than zero.")
        employee_id = normalize_employee_id(employee_id)
        if employee_id is None:
            return False, None, None, {}
        cursor = self.next_work(employee_id, pd.Timestamp(earliest))
        if cursor is None:
            return False, None, None, {}
        start = cursor
        remaining = float(duration_hours)
        allocations = defaultdict(float, weekly_allocations or {})
        consumed: dict[int, float] = defaultdict(float)
        horizon_end = self.horizon_end(employee_id)
        while remaining > 1e-9:
            cursor = self.next_work(employee_id, cursor)
            if cursor is None or (horizon_end is not None and cursor > horizon_end):
                return False, None, None, {}
            period = next((period for period in work_periods(cursor) if period[0] <= cursor < period[1]), None)
            if period is None:
                cursor = self.next_work(employee_id, cursor + pd.Timedelta("1s"))
                if cursor is None:
                    return False, None, None, {}
                continue
            _, period_end = period
            week = iso_week(cursor)
            allowed_this_week = max(0.0, MAX_WEEKLY_HOURS - allocations[week])
            available_hours = (period_end - cursor).total_seconds() / 3600.0
            block = min(remaining, available_hours, allowed_this_week)
            if block <= 1e-9:
                cursor = self.next_work(employee_id, period_end + pd.Timedelta(seconds=1))
                if cursor is None:
                    return False, None, None, {}
                continue
            cursor += pd.to_timedelta(float(block), unit="h")
            remaining -= block
            allocations[week] += block
            consumed[week] += block
            if remaining > 1e-9:
                cursor = self.next_work(employee_id, cursor + pd.Timedelta("1s"))
                if cursor is None:
                    return False, None, None, {}
        return True, start, cursor, dict(consumed)

    def calculate_busy_until(self, employee_id: object, remaining_hours: float, start_time: pd.Timestamp) -> pd.Timestamp | None:
        if remaining_hours <= 0:
            return pd.Timestamp(start_time)
        can_finish, _, end, _ = self.task_schedule(employee_id, start_time, remaining_hours)
        return end if can_finish else None

    def calculate_available_at(self, employee_id: object, remaining_hours: float, start_time: pd.Timestamp) -> pd.Timestamp | None:
        busy_until = self.calculate_busy_until(employee_id, remaining_hours, start_time)
        if busy_until is None:
            return None
        return self.next_work(employee_id, busy_until + pd.to_timedelta(int(POST_TASK_BREAK_MINUTES), unit="min"))
