"""Authoritative scheduling engine extracted from Untitled6.ipynb.

The engine is intentionally pandas/Python only, so it can be imported from a
notebook, exercised by tests, or rendered by the Streamlit application.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .api import AssignmentRegistrar, TriwebApiClient
from .availability import AvailabilityCalendar, prepare_availability
from .config import REGISTRY_FILE, SCHEDULABLE_DEPARTMENTS, employees_file
from .employees import build_active_employees, load_employees, normalize_employee_id
from .projects import (
    build_employee_workload,
    clean_status,
    prepare_projects,
    remaining_stage_hours,
    scheduler_pool,
    stage_expected_hours,
    stage_is_finished,
    stage_needs_assignment,
    stage_values,
    update_local_assignment,
)
from .state import AssignmentRegistry


STATE_COLUMNS = [
    "EmployeeID", "EmployeeName", "Department", "CurrentProject", "CurrentStatus",
    "CurrentWorkedSeconds", "RemainingHours", "BusyUntil", "AvailableAt",
    "QueuedProjects", "QueuedProjectIDs", "PausedProjects", "PausedProjectIDs",
    "ProductionProjects", "IsCurrentlyBusy", "ScheduledProjects", "WeeklyAllocation",
]


@dataclass
class SchedulerSnapshot:
    refreshed_at: datetime
    raw_availability: pd.DataFrame
    raw_projects: pd.DataFrame
    employees: pd.DataFrame
    availability: pd.DataFrame
    projects: pd.DataFrame
    workload: pd.DataFrame
    employee_state: pd.DataFrame
    scheduler_state: pd.DataFrame
    scheduler_projects: pd.DataFrame
    assignments: pd.DataFrame = field(default_factory=pd.DataFrame)


def _empty_assignments() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "ProjectID", "Department", "EmployeeID", "EmployeeName", "Start", "End",
        "DurationHours", "Priority", "Nature", "Performance", "QueuedProjects",
        "PausedProjects", "ProductionProjects", "WeeklyAllocation", "Status", "Reason",
    ])


def build_employee_current_state(active_employees: pd.DataFrame, workload: pd.DataFrame) -> pd.DataFrame:
    """Derive CurrentProject, queues, pauses, and Production workload from the API."""
    records: list[dict[str, Any]] = []
    for _, employee in active_employees.iterrows():
        employee_id = normalize_employee_id(employee["EmployeeID"])
        if employee_id is None or employee["Department"] not in SCHEDULABLE_DEPARTMENTS:
            continue
        employee_projects = workload[workload["EmployeeID"].eq(employee_id)].copy()
        working = employee_projects[employee_projects["Status"].eq("en cours")]
        if len(working) > 1:
            raise ValueError(f"Employee {employee_id} has multiple 'En cours' production projects.")
        current = working.iloc[0] if not working.empty else None
        assigned = employee_projects[employee_projects["Status"].eq("affecté")]
        paused = employee_projects[employee_projects["Status"].eq("en pause")]
        records.append({
            "EmployeeID": employee_id,
            "EmployeeName": employee["EmployeeName"],
            "Department": employee["Department"],
            "CurrentProject": None if current is None else current["ProjectID"],
            "CurrentStatus": "Available" if current is None else "En cours",
            "CurrentWorkedSeconds": np.nan if current is None else current["WorkedSeconds"],
            "QueuedProjects": len(assigned), "QueuedProjectIDs": assigned["ProjectID"].tolist(),
            "PausedProjects": len(paused), "PausedProjectIDs": paused["ProjectID"].tolist(),
            "ProductionProjects": len(employee_projects), "IsCurrentlyBusy": current is not None,
        })
    if not records:
        return pd.DataFrame(columns=STATE_COLUMNS)
    return pd.DataFrame(records).sort_values(["Department", "EmployeeName"]).reset_index(drop=True)


def build_employee_scheduler_state(
    active_employees: pd.DataFrame,
    employee_current_state: pd.DataFrame,
    workload: pd.DataFrame,
    calendar: AvailabilityCalendar,
    planning_start: pd.Timestamp,
) -> pd.DataFrame:
    """Add remaining work, BusyUntil and AvailableAt to the current API workload."""
    records: list[dict[str, Any]] = []
    for _, employee in active_employees.iterrows():
        employee_id = normalize_employee_id(employee["EmployeeID"])
        if employee_id is None or employee["Department"] not in SCHEDULABLE_DEPARTMENTS:
            continue
        matching_state = employee_current_state[employee_current_state["EmployeeID"].eq(employee_id)]
        if matching_state.empty:
            continue
        state = matching_state.iloc[0]
        current_project = state["CurrentProject"]
        current_worked_seconds: object = np.nan
        remaining_hours = 0.0
        busy_until: pd.Timestamp | None = None
        available_at: pd.Timestamp | None
        if current_project is not None:
            current_rows = workload[
                workload["EmployeeID"].eq(employee_id)
                & workload["Department"].eq(employee["Department"])
                & workload["ProjectID"].astype(str).eq(str(current_project))
            ]
            if current_rows.empty:
                available_at = None
            else:
                current = current_rows.iloc[0]
                current_worked_seconds = current["WorkedSeconds"]
                calculated_remaining = remaining_stage_hours(current["Nature"], employee["Department"], current_worked_seconds)
                remaining_hours = 0.0 if calculated_remaining is None else calculated_remaining
                busy_until = calendar.calculate_busy_until(employee_id, remaining_hours, planning_start)
                available_at = calendar.calculate_available_at(employee_id, remaining_hours, planning_start) if busy_until is not None else None
        else:
            available_at = calendar.next_work(employee_id, planning_start)
        records.append({
            "EmployeeID": employee_id, "EmployeeName": employee["EmployeeName"], "Department": employee["Department"],
            "CurrentProject": current_project, "CurrentStatus": state["CurrentStatus"],
            "CurrentWorkedSeconds": current_worked_seconds, "RemainingHours": remaining_hours,
            "BusyUntil": busy_until, "AvailableAt": available_at,
            "QueuedProjects": int(state["QueuedProjects"]), "QueuedProjectIDs": list(state["QueuedProjectIDs"]),
            "PausedProjects": int(state["PausedProjects"]), "PausedProjectIDs": list(state["PausedProjectIDs"]),
            "ProductionProjects": int(state["ProductionProjects"]), "IsCurrentlyBusy": bool(state["IsCurrentlyBusy"]),
            "ScheduledProjects": [], "WeeklyAllocation": {},
        })
    if not records:
        return pd.DataFrame(columns=STATE_COLUMNS)
    return pd.DataFrame(records).sort_values(["Department", "AvailableAt", "EmployeeName"], na_position="last").reset_index(drop=True)


def unit_score(value: object) -> float:
    score = pd.to_numeric(value, errors="coerce")
    if pd.isna(score) or not np.isfinite(score):
        return 0.0
    return float(np.clip(float(score) / 100.0 if float(score) > 1 else float(score), 0.0, 1.0))


def performance_score(candidate: pd.Series, priority: object) -> float:
    """Exact final-notebook performance rule: priority <= 2 changes weights."""
    priority_value = pd.to_numeric(priority, errors="coerce")
    quality, rapidity, confidence = (0.50, 0.30, 0.20) if pd.notna(priority_value) and priority_value <= 2 else (0.80, 0.10, 0.10)
    return quality * unit_score(candidate["QualityScore"]) + rapidity * unit_score(candidate["RapidityScore"]) + confidence * unit_score(candidate["Confidence"])


def rank_candidates(candidates: pd.DataFrame, priority: object) -> pd.DataFrame:
    """Notebook order: performance, earliest feasible start, lower workload, ID."""
    if candidates.empty:
        return candidates.copy()
    ranked = candidates.copy()
    ranked["Performance"] = ranked.apply(lambda row: performance_score(row, priority), axis=1)
    ranked["Workload"] = ranked["QueuedProjects"] + ranked["PausedProjects"]
    ranked = ranked.sort_values(["Performance", "Start", "Workload", "EmployeeID"], ascending=[False, True, True, True]).reset_index(drop=True)
    ranked["Rank"] = range(1, len(ranked) + 1)
    return ranked


class SchedulerEngine:
    """Refresh, reconstruct, rank, and calculate a non-destructive schedule."""

    def __init__(
        self,
        employee_csv: Path | None = None,
        api_client: TriwebApiClient | None = None,
        registry_file: Path = REGISTRY_FILE,
    ) -> None:
        self.employee_csv = employee_csv or employees_file()
        self.api_client = api_client or TriwebApiClient()
        self.registry = AssignmentRegistry(registry_file)
        self.registrar = AssignmentRegistrar()

    def refresh(self, planning_start: pd.Timestamp | None = None) -> SchedulerSnapshot:
        """Fetch both live APIs and rebuild every scheduler state from scratch."""
        return self.build_snapshot(
            employees=load_employees(self.employee_csv),
            availability_raw=self.api_client.fetch_availability(),
            projects_raw=self.api_client.fetch_projects(),
            planning_start=planning_start,
        )

    def build_snapshot(
        self,
        employees: pd.DataFrame,
        availability_raw: list[dict] | pd.DataFrame,
        projects_raw: list[dict] | pd.DataFrame,
        planning_start: pd.Timestamp | None = None,
    ) -> SchedulerSnapshot:
        """Pure data path used by both API refresh and repeatable notebook tests."""
        planning_start = pd.Timestamp.now().floor("min") if planning_start is None else pd.Timestamp(planning_start)
        availability = prepare_availability(availability_raw)
        active_employees = build_active_employees(employees, availability)
        active_ids = set(active_employees["EmployeeID"])
        projects = prepare_projects(projects_raw, today=planning_start)
        workload = build_employee_workload(projects, active_ids)
        current_state = build_employee_current_state(active_employees, workload)
        calendar = AvailabilityCalendar(availability, active_ids)
        state = build_employee_scheduler_state(active_employees, current_state, workload, calendar, planning_start)
        self.registry.reconcile(projects)
        return SchedulerSnapshot(
            refreshed_at=datetime.now(timezone.utc), raw_availability=pd.DataFrame(availability_raw).copy(), raw_projects=pd.DataFrame(projects_raw).copy(), employees=active_employees, availability=availability,
            projects=projects, workload=workload, employee_state=current_state, scheduler_state=state,
            scheduler_projects=scheduler_pool(projects), assignments=_empty_assignments(),
        )

    @staticmethod
    def _clone_state(state: pd.DataFrame) -> pd.DataFrame:
        copied = state.copy(deep=True)
        for column in ("QueuedProjectIDs", "PausedProjectIDs", "ScheduledProjects", "WeeklyAllocation"):
            if column in copied:
                copied[column] = copied[column].map(lambda value: list(value) if isinstance(value, list) else dict(value) if isinstance(value, dict) else value)
        return copied

    def _calendar(self, snapshot: SchedulerSnapshot) -> AvailabilityCalendar:
        return AvailabilityCalendar(snapshot.availability, set(snapshot.employees["EmployeeID"]))

    def _employee_name(self, snapshot: SchedulerSnapshot, employee_id: object) -> object:
        normalized = normalize_employee_id(employee_id)
        matches = snapshot.employees[snapshot.employees["EmployeeID"].eq(normalized)]
        return pd.NA if matches.empty else matches.iloc[0]["EmployeeName"]

    def _candidates_for_stage(
        self,
        snapshot: SchedulerSnapshot,
        state: pd.DataFrame,
        project: pd.Series,
        department: str,
        earliest: pd.Timestamp,
    ) -> pd.DataFrame:
        duration_hours = stage_expected_hours(project["Nature"], department)
        if duration_hours is None:
            return pd.DataFrame()
        calendar = self._calendar(snapshot)
        records: list[dict[str, Any]] = []
        qualified = snapshot.employees[snapshot.employees["Department"].eq(department)]
        for _, employee in qualified.iterrows():
            employee_id = employee["EmployeeID"]
            rows = state[state["EmployeeID"].eq(employee_id)]
            if rows.empty:
                continue
            employee_state = rows.iloc[0]
            # Fundamental eligibility rule from the validated notebook.
            if employee_state["CurrentProject"] is not None or bool(employee_state["IsCurrentlyBusy"]) or int(employee_state["QueuedProjects"]) > 0:
                continue
            available_at = employee_state["AvailableAt"]
            if pd.isna(available_at):
                continue
            start_after = max(pd.Timestamp(earliest), pd.Timestamp(available_at))
            can_finish, start, end, weekly_allocation = calendar.task_schedule(
                employee_id, start_after, duration_hours, employee_state["WeeklyAllocation"]
            )
            if not can_finish:
                continue
            records.append({
                "EmployeeID": employee_id, "EmployeeName": employee["EmployeeName"], "Department": department,
                "Start": start, "End": end, "DurationHours": duration_hours,
                "QualityScore": employee["QualityScore"], "RapidityScore": employee["RapidityScore"], "Confidence": employee["Confidence"],
                "QueuedProjects": int(employee_state["QueuedProjects"]), "PausedProjects": int(employee_state["PausedProjects"]),
                "ProductionProjects": int(employee_state["ProductionProjects"]), "WeeklyAllocation": weekly_allocation,
            })
        return pd.DataFrame(records).sort_values(["Start", "EmployeeName"]).reset_index(drop=True) if records else pd.DataFrame()

    def _register_scheduled_assignment(
        self, state: pd.DataFrame, chosen: pd.Series, project_id: object, department: str, calendar: AvailabilityCalendar
    ) -> None:
        matches = state.index[state["EmployeeID"].eq(chosen["EmployeeID"])]
        if len(matches) != 1:
            raise ValueError(f"Employee {chosen['EmployeeID']} not found uniquely in scheduler state.")
        index = matches[0]
        state.at[index, "ScheduledProjects"].append({"ProjectID": str(project_id), "Department": department, "Start": chosen["Start"], "End": chosen["End"]})
        state.at[index, "QueuedProjects"] = int(state.at[index, "QueuedProjects"]) + 1
        state.at[index, "ProductionProjects"] = int(state.at[index, "ProductionProjects"]) + 1
        current_weeks = dict(state.at[index, "WeeklyAllocation"])
        for week, hours in chosen["WeeklyAllocation"].items():
            current_weeks[int(week)] = current_weeks.get(int(week), 0.0) + float(hours)
        state.at[index, "WeeklyAllocation"] = current_weeks
        available_at = calendar.next_work(chosen["EmployeeID"], pd.Timestamp(chosen["End"]) + pd.Timedelta("20min"))
        if available_at is not None:
            state.at[index, "AvailableAt"] = max(pd.Timestamp(state.at[index, "AvailableAt"]), pd.Timestamp(available_at))

    def _assignment_record(self, project: pd.Series, department: object, **updates: Any) -> dict[str, Any]:
        record = {
            "ProjectID": str(project["ProjectID"]), "Department": department, "EmployeeID": pd.NA, "EmployeeName": pd.NA,
            "Start": pd.NaT, "End": pd.NaT, "DurationHours": pd.NA, "Priority": project["Priority"], "Nature": project["Nature"],
            "Client": project.get("ClientName", project.get("ClientCode", pd.NA)),
            "ReceptionDate": project.get("ReceptionDateParsed", pd.NaT), "DeliveryDate": project.get("DeliveryDate", pd.NA),
            "CurrentStage": department,
            "Performance": np.nan, "QueuedProjects": np.nan, "PausedProjects": np.nan, "ProductionProjects": np.nan,
            "WeeklyAllocation": {}, "Status": "Waiting", "Reason": "",
        }
        record.update(updates)
        return record

    def _schedule_project(self, snapshot: SchedulerSnapshot, state: pd.DataFrame, source_project: pd.Series, planning_start: pd.Timestamp) -> list[dict[str, Any]]:
        project = source_project.copy()  # never mutate the API snapshot
        workflow = project["Workflow"]
        if workflow is None:
            return [self._assignment_record(project, pd.NA, Reason="Unknown workflow")]
        calendar = self._calendar(snapshot)
        assignments: list[dict[str, Any]] = []
        ready_at = planning_start
        for department in workflow:
            if stage_is_finished(project, department):
                continue
            if stage_needs_assignment(project, department):
                if self.registry.has_local_assignment(project["ProjectID"], department):
                    assignments.append(self._assignment_record(project, department, Status="Pending registration", Reason="Local scheduler assignment already exists; awaiting Triweb confirmation."))
                    break
                candidates = self._candidates_for_stage(snapshot, state, project, department, ready_at)
                if candidates.empty:
                    assignments.append(self._assignment_record(project, department, DurationHours=stage_expected_hours(project["Nature"], department), Reason="No feasible employee available within the live availability horizon."))
                    break
                chosen = rank_candidates(candidates, project["Priority"]).iloc[0]
                self._register_scheduled_assignment(state, chosen, project["ProjectID"], department, calendar)
                update_local_assignment(project, department, chosen["EmployeeID"])
                assignment = self._assignment_record(
                    project, department, EmployeeID=chosen["EmployeeID"], EmployeeName=chosen["EmployeeName"],
                    Start=chosen["Start"], End=chosen["End"], DurationHours=chosen["DurationHours"],
                    Performance=chosen["Performance"], QueuedProjects=chosen["QueuedProjects"], PausedProjects=chosen["PausedProjects"],
                    ProductionProjects=chosen["ProductionProjects"], WeeklyAllocation=chosen["WeeklyAllocation"],
                    Status="Calculated", Reason="Best feasible candidate",
                )
                self.registry.record(assignment)
                assignments.append(assignment)
                ready_at = pd.Timestamp(chosen["End"])
                continue
            employee_id, status, worked_seconds = stage_values(project, department)
            normalized_id = normalize_employee_id(employee_id)
            if clean_status(status) == "en cours":
                remaining = remaining_stage_hours(project["Nature"], department, worked_seconds)
                busy_until = calendar.calculate_busy_until(normalized_id, remaining, planning_start) if remaining is not None else None
                assignments.append(self._assignment_record(
                    project, department, EmployeeID=normalized_id, EmployeeName=self._employee_name(snapshot, normalized_id), End=busy_until if busy_until is not None else pd.NaT,
                    Reason="Stage currently in progress; downstream stage must wait" if busy_until is not None else "Current stage is in progress but finish time could not be estimated.",
                ))
                break
            assignments.append(self._assignment_record(
                project, department, EmployeeID=normalized_id, EmployeeName=self._employee_name(snapshot, normalized_id),
                Reason=f"{department} stage is '{clean_status(status)}' and is not finished.",
            ))
            break
        return assignments

    def run_scheduler(self, snapshot: SchedulerSnapshot, planning_start: pd.Timestamp | None = None) -> SchedulerSnapshot:
        """Calculate only new assignments, preserving registry idempotency."""
        planning_start = pd.Timestamp.now().floor("min") if planning_start is None else pd.Timestamp(planning_start)
        state = self._clone_state(snapshot.scheduler_state)
        records: list[dict[str, Any]] = []
        for _, project in snapshot.scheduler_projects.iterrows():
            try:
                records.extend(self._schedule_project(snapshot, state, project, planning_start))
            except Exception as exc:
                records.append(self._assignment_record(project, pd.NA, Status="Error", Reason=str(exc)))
        snapshot.scheduler_state = state
        snapshot.assignments = pd.DataFrame(records) if records else _empty_assignments()
        return snapshot

    def registry_assignments(self) -> pd.DataFrame:
        return self.registry.assignments()

    def register_pending_assignments(self) -> None:
        """Reserved controlled hand-off point; never fabricate a Triweb write request."""
        for _, assignment in self.registry.pending().iterrows():
            self.registrar.register(assignment.to_dict())


def snapshot_metrics(snapshot: SchedulerSnapshot, registry_assignments: pd.DataFrame) -> dict[str, int]:
    state = snapshot.scheduler_state
    assignments = snapshot.assignments
    return {
        "Active employees": len(snapshot.employees),
        "Currently busy": int(state["IsCurrentlyBusy"].sum()) if not state.empty else 0,
        "Currently free": int((~state["IsCurrentlyBusy"]).sum()) if not state.empty else 0,
        "Projects in API": len(snapshot.projects),
        "Projects received last 15 days": int(snapshot.projects["RecentEnough"].sum()),
        "Projects waiting assignment": len(snapshot.scheduler_projects),
        "Assignments generated": int(assignments["Status"].eq("Calculated").sum()) if not assignments.empty else 0,
        "Assignments pending registration": int(registry_assignments["Status"].eq("Pending registration").sum()) if not registry_assignments.empty and "Status" in registry_assignments else 0,
    }
