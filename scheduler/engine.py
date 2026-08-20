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
    def _register_reserved_assignment(
        self,
        state: pd.DataFrame,
        employee_id: object,
        project_id: object,
        department: str,
    ) -> None:
        """
        Reserve an employee for a future workflow stage.

        No Start/End exists yet because the upstream stage
        has no known finish time.
        """

        matches = state.index[
            state["EmployeeID"].eq(
                normalize_employee_id(employee_id)
            )
        ]

        if len(matches) != 1:
            raise ValueError(
                f"Employee {employee_id} not found uniquely."
            )

        index = matches[0]

        state.at[
            index,
            "ScheduledProjects"
        ].append({
            "ProjectID": str(project_id),
            "Department": department,
            "Start": pd.NaT,
            "End": pd.NaT,
            "Reserved": True,
        })

        # Important:
        # This prevents the employee from being selected
        # for another project during this scheduler run.
        state.at[
            index,
            "QueuedProjects"
        ] = (
            int(
                state.at[
                    index,
                    "QueuedProjects"
                ]
            ) + 1
        )

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
            # ----------------------------------------------------
            # HARD RULE:
            # An employee already reserved by this scheduler run
            # cannot receive another project.
            # ----------------------------------------------------

            scheduled_projects = employee_state.get(
                "ScheduledProjects",
                []
            )

            if isinstance(scheduled_projects, list) and scheduled_projects:
                continue
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
    def _employee_has_local_reservation(
        self,
        employee_id: object,
        current_project_id: object,
        current_department: str,
    ) -> bool:
        """
        Return True when the employee is already reserved by
        another local scheduler assignment that Triweb has not
        confirmed yet.
        """

        registry = self.registry.assignments()

        if registry.empty:
            return False

        employee_id = normalize_employee_id(
            employee_id
        )

        current_project_id = str(
            current_project_id
        )

        blocking_statuses = {
            "Calculated",
            "Pending registration",
            "Reserved",
        }

        registry = registry.copy()

        registry["_EmployeeID"] = (
            registry["EmployeeID"]
            .apply(normalize_employee_id)
        )

        registry["_ProjectID"] = (
            registry["ProjectID"]
            .astype(str)
        )

        for _, row in registry.iterrows():

            if row["_EmployeeID"] != employee_id:
                continue

            # Same project is allowed
            if row["_ProjectID"] == current_project_id:
                continue

            if row.get("Status") in blocking_statuses:
                return True

        return False
    def _reservation_candidates_for_stage(
        self,
        snapshot: SchedulerSnapshot,
        state: pd.DataFrame,
        project: pd.Series,
        department: str,
    ) -> pd.DataFrame:
        """
        Find employees who can be reserved for a future workflow stage.

        No concrete Start/End is calculated because the previous
        stage does not have a known finish time.
        """

        records = []

        qualified = snapshot.employees[
            snapshot.employees["Department"].eq(department)
        ]

        for _, employee in qualified.iterrows():

            employee_id = employee["EmployeeID"]

            employee_rows = state[
                state["EmployeeID"].eq(employee_id)
            ]

            if employee_rows.empty:
                continue

            employee_state = employee_rows.iloc[0]

            # Already working
            if employee_state["CurrentProject"] is not None:
                continue

            if bool(employee_state["IsCurrentlyBusy"]):
                continue

            # Already has queued work
            if int(employee_state["QueuedProjects"]) > 0:
                continue

            available_at = employee_state["AvailableAt"]

            if pd.isna(available_at):
                continue

            records.append({
                "EmployeeID": employee_id,
                "EmployeeName": employee["EmployeeName"],
                "Department": department,

                # Only used to rank earliest availability
                "Start": pd.Timestamp(available_at),

                # Unknown because upstream finish is unknown
                "End": pd.NaT,

                "DurationHours": stage_expected_hours(
                    project["Nature"],
                    department,
                ),

                "QualityScore": employee["QualityScore"],
                "RapidityScore": employee["RapidityScore"],
                "Confidence": employee["Confidence"],

                "QueuedProjects": int(
                    employee_state["QueuedProjects"]
                ),

                "PausedProjects": int(
                    employee_state["PausedProjects"]
                ),

                "ProductionProjects": int(
                    employee_state["ProductionProjects"]
                ),

                "WeeklyAllocation": employee_state[
                    "WeeklyAllocation"
                ],
            })

        if not records:
            return pd.DataFrame()

        return (
            pd.DataFrame(records)
            .sort_values(
                ["Start", "EmployeeName"]
            )
            .reset_index(drop=True)
        )
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

    def _apply_active_local_assignments(
        self,
        snapshot: SchedulerSnapshot,
        state: pd.DataFrame,
        planning_start: pd.Timestamp,
    ) -> None:
        """
        Load valid local scheduler reservations into the live
        scheduler state so an employee cannot be assigned again.

        Rules:
            - API-confirmed assignments are already represented by
            the live state and are not added again.
            - Local assignments starting before planning_start are
            considered stale unless the API says the stage is
            actually En cours.
            - Future Pending registration / Reserved assignments
            block the employee.
        """

        registry = self.registry.assignments()

        if registry.empty:
            return

        for _, assignment in registry.iterrows():

            status = str(
                assignment.get("Status", "")
            ).strip().casefold()

            if status not in {
                "pending registration",
                "reserved",
                "calculated",
            }:
                continue

            project_id = str(
                assignment["ProjectID"]
            )

            department = str(
                assignment["Department"]
            )

            # ----------------------------------------------------
            # Find project in live API
            # ----------------------------------------------------

            matches = snapshot.projects[
                snapshot.projects["ProjectID"]
                .astype(str)
                .eq(project_id)
            ]

            if matches.empty:
                continue

            project = matches.iloc[0]

            # ----------------------------------------------------
            # If API already has a real employee for this stage,
            # this is API truth. Registry does not block anything.
            # ----------------------------------------------------

            if department == "Redaction":

                api_employee = normalize_employee_id(
                    project["RedactorID"]
                )

            elif department == "Graphe":

                api_employee = normalize_employee_id(
                    project["GraphistID"]
                )

            else:
                continue

            if api_employee not in (None, "0"):
                continue

            # ----------------------------------------------------
            # Check local timing
            # ----------------------------------------------------

            start = pd.to_datetime(
                assignment.get("Start"),
                errors="coerce",
            )

            end = pd.to_datetime(
                assignment.get("End"),
                errors="coerce",
            )

            # Old local assignment
            if pd.notna(start) and start < planning_start:

                # If API says it is actually in progress, don't
                # treat it as stale.
                if department == "Redaction":
                    live_status = clean_status(
                        project["RedacStatus"]
                    )
                else:
                    live_status = clean_status(
                        project["GraphStatus"]
                    )

                if live_status != "en cours":
                    continue

            employee_id = normalize_employee_id(
                assignment.get("EmployeeID")
            )

            if employee_id is None:
                continue

            employee_rows = state[
                state["EmployeeID"].apply(
                    normalize_employee_id
                ).eq(employee_id)
            ]

            if employee_rows.empty:
                continue

            index = employee_rows.index[0]

            # ----------------------------------------------------
            # Block employee
            # ----------------------------------------------------

            scheduled = list(
                state.at[
                    index,
                    "ScheduledProjects"
                ]
            )

            scheduled.append({
                "ProjectID": project_id,
                "Department": department,
                "Start": start,
                "End": end,
                "Reserved": (
                    status == "reserved"
                ),
            })

            state.at[
                index,
                "ScheduledProjects"
            ] = scheduled

            state.at[
                index,
                "QueuedProjects"
            ] = (
                int(
                    state.at[
                        index,
                        "QueuedProjects"
                    ]
                ) + 1
            )
    
    def _schedule_project(
        self,
        snapshot: SchedulerSnapshot,
        state: pd.DataFrame,
        source_project: pd.Series,
        planning_start: pd.Timestamp,
    ) -> list[dict[str, Any]]:

        project = source_project.copy()

        workflow = project["Workflow"]

        if workflow is None:
            return [
                self._assignment_record(
                    project,
                    pd.NA,
                    Reason="Unknown workflow",
                )
            ]

        calendar = self._calendar(snapshot)

        assignments = []

        # Earliest known start time for the next stage
        ready_at = pd.Timestamp(planning_start)

        # True when an upstream stage exists but its finish time
        # is not known yet.
        dependency_unknown = False

        previous_department = None

        # ========================================================
        # PROCESS PROJECT WORKFLOW
        # ========================================================

        for department in workflow:

            # ----------------------------------------------------
            # Stage already finished
            # ----------------------------------------------------

            if stage_is_finished(
                project,
                department
            ):
                previous_department = department
                continue

            # ====================================================
            # STAGE NEEDS ASSIGNMENT
            # ====================================================

            if stage_needs_assignment(
                project,
                department
            ):

                # ------------------------------------------------
                # CASE A:
                # Previous stage has unknown finish time
                #
                # Example:
                # Redaction = Affecté
                # Graphe = En instance
                # ------------------------------------------------

                if dependency_unknown:

                    candidates = (
                        self._reservation_candidates_for_stage(
                            snapshot=snapshot,
                            state=state,
                            project=project,
                            department=department,
                        )
                    )

                    if candidates.empty:

                        assignments.append(
                            self._assignment_record(
                                project,
                                department,
                                Status="Waiting",
                                Reason=(
                                    "No employee available for "
                                    "future reservation."
                                ),
                            )
                        )

                        break

                    # Rank available employees.
                    #
                    # We use available_at as Start only for ranking.
                    ranked = rank_candidates(
                        candidates,
                        project["Priority"],
                    )

                    chosen = ranked.iloc[0]

                    employee_id = chosen["EmployeeID"]

                    # --------------------------------------------
                    # Reserve employee locally
                    # --------------------------------------------

                    self._register_reserved_assignment(
                        state=state,
                        employee_id=employee_id,
                        project_id=project["ProjectID"],
                        department=department,
                    )

                    # --------------------------------------------
                    # Update local project copy
                    # --------------------------------------------

                    update_local_assignment(
                        project,
                        department,
                        employee_id,
                    )

                    reservation = self._assignment_record(
                        project,
                        department,

                        EmployeeID=employee_id,

                        EmployeeName=(
                            chosen["EmployeeName"]
                        ),

                        Start=pd.NaT,
                        End=pd.NaT,

                        DurationHours=pd.NA,

                        Performance=(
                            chosen["Performance"]
                        ),

                        QueuedProjects=(
                            chosen["QueuedProjects"]
                        ),

                        PausedProjects=(
                            chosen["PausedProjects"]
                        ),

                        ProductionProjects=(
                            chosen["ProductionProjects"]
                        ),

                        WeeklyAllocation=(
                            chosen["WeeklyAllocation"]
                        ),

                        Status="Reserved",

                        Reason=(
                            "Employee reserved now; "
                            "start will be scheduled after "
                            f"{previous_department} "
                            "finishes."
                        ),
                    )

                    if not self.registry.has_local_assignment(
                        project["ProjectID"],
                        department,
                    ):
                        self.registry.record(
                            reservation
                        )

                    assignments.append(
                        reservation
                    )

                    # Continue workflow
                    previous_department = department
                    continue

                # ------------------------------------------------
                # CASE B:
                # Normal scheduling with known earliest start
                # ------------------------------------------------

                if self.registry.has_local_assignment(
                    project["ProjectID"],
                    department,
                ):

                    registry = (
                        self.registry.assignments()
                    )

                    existing = registry[
                        registry["ProjectID"]
                        .astype(str)
                        .eq(
                            str(project["ProjectID"])
                        )
                        &
                        registry["Department"]
                        .astype(str)
                        .eq(
                            str(department)
                        )
                    ].copy()

                    if not existing.empty:

                        existing_row = (
                            existing.iloc[-1]
                        )

                        existing_employee = (
                            normalize_employee_id(
                                existing_row[
                                    "EmployeeID"
                                ]
                            )
                        )

                        existing_end = pd.to_datetime(
                            existing_row.get("End"),
                            errors="coerce",
                        )

                        update_local_assignment(
                            project,
                            department,
                            existing_employee,
                        )

                        assignments.append(
                            self._assignment_record(
                                project,
                                department,

                                EmployeeID=existing_employee,

                                EmployeeName=(
                                    self._employee_name(
                                        snapshot,
                                        existing_employee,
                                    )
                                ),

                                Start=pd.to_datetime(
                                    existing_row.get("Start"),
                                    errors="coerce",
                                ),

                                End=existing_end,

                                DurationHours=(
                                    existing_row.get(
                                        "DurationHours",
                                        pd.NA,
                                    )
                                ),

                                Performance=(
                                    existing_row.get(
                                        "Performance",
                                        np.nan,
                                    )
                                ),

                                Status=(
                                    existing_row.get(
                                        "Status",
                                        "Pending registration",
                                    )
                                ),

                                Reason=(
                                    "Local scheduler assignment "
                                    "already exists."
                                ),
                            )
                        )

                        # If we know the end, the next stage can
                        # start after it.
                        if pd.notna(existing_end):

                            ready_at = max(
                                ready_at,
                                pd.Timestamp(existing_end),
                            )

                        else:

                            dependency_unknown = True

                        previous_department = department
                        continue

                # ------------------------------------------------
                # Find normal candidates
                # ------------------------------------------------

                candidates = (
                    self._candidates_for_stage(
                        snapshot,
                        state,
                        project,
                        department,
                        ready_at,
                    )
                )

                if candidates.empty:

                    assignments.append(
                        self._assignment_record(
                            project,
                            department,
                            DurationHours=(
                                stage_expected_hours(
                                    project["Nature"],
                                    department,
                                )
                            ),
                            Status="Waiting",
                            Reason=(
                                "No feasible employee available "
                                "within the live availability horizon."
                            ),
                        )
                    )

                    break

                ranked = rank_candidates(
                    candidates,
                    project["Priority"],
                )

                chosen = ranked.iloc[0]

                employee_id = chosen[
                    "EmployeeID"
                ]

                # ----------------------------------------------
                # Register normal scheduled assignment
                # ----------------------------------------------

                self._register_scheduled_assignment(
                    state=state,
                    chosen=chosen,
                    project_id=project["ProjectID"],
                    department=department,
                    calendar=calendar,
                )

                update_local_assignment(
                    project,
                    department,
                    employee_id,
                )

                assignment = self._assignment_record(
                    project,
                    department,

                    EmployeeID=employee_id,
                    EmployeeName=chosen["EmployeeName"],

                    Start=chosen["Start"],
                    End=chosen["End"],

                    DurationHours=chosen[
                        "DurationHours"
                    ],

                    Performance=chosen[
                        "Performance"
                    ],

                    QueuedProjects=chosen[
                        "QueuedProjects"
                    ],

                    PausedProjects=chosen[
                        "PausedProjects"
                    ],

                    ProductionProjects=chosen[
                        "ProductionProjects"
                    ],

                    WeeklyAllocation=chosen[
                        "WeeklyAllocation"
                    ],

                    Status="Calculated",

                    Reason="Best feasible candidate",
                )

                                # ----------------------------------------------------
                # Save only if this ProjectID + Department does not
                # already exist in the local registry.
                # ----------------------------------------------------

                if not self.registry.has_local_assignment(
                    project["ProjectID"],
                    department,
                ):
                    self.registry.record(
                        assignment
                    )

                assignments.append(
                    assignment
                )

                ready_at = pd.Timestamp(
                    chosen["End"]
                )

                previous_department = department

                continue

            # ====================================================
            # EXISTING STAGE
            # ====================================================

            employee_id, status, worked_seconds = (
                stage_values(
                    project,
                    department,
                )
            )

            normalized_id = normalize_employee_id(
                employee_id
            )

            clean_stage_status = clean_status(
                status
            )

            # ====================================================
            # EN COURS
            # ====================================================

            if clean_stage_status == "en cours":

                remaining = remaining_stage_hours(
                    project["Nature"],
                    department,
                    worked_seconds,
                )

                busy_until = (
                    calendar.calculate_busy_until(
                        normalized_id,
                        remaining,
                        planning_start,
                    )
                    if remaining is not None
                    else None
                )

                assignments.append(
                    self._assignment_record(
                        project,
                        department,

                        EmployeeID=normalized_id,

                        EmployeeName=(
                            self._employee_name(
                                snapshot,
                                normalized_id,
                            )
                        ),

                        Start=pd.NaT,

                        End=(
                            busy_until
                            if busy_until is not None
                            else pd.NaT
                        ),

                        Status="Waiting",

                        Reason=(
                            "Stage currently in progress; "
                            "downstream stage can be assigned "
                            "now."
                        ),
                    )
                )

                if busy_until is not None:

                    ready_at = max(
                        ready_at,
                        pd.Timestamp(busy_until),
                    )

                    # IMPORTANT:
                    # Continue to Graphe.
                    dependency_unknown = False

                else:

                    # We don't know when this stage finishes.
                    # The downstream stage can still be RESERVED.
                    dependency_unknown = True

                previous_department = department

                continue

            # ====================================================
            # AFFECTÉ / EN PAUSE
            # ====================================================

            if clean_stage_status in {
                "affecté",
                "en pause",
            }:

                assignments.append(
                    self._assignment_record(
                        project,
                        department,

                        EmployeeID=normalized_id,

                        EmployeeName=(
                            self._employee_name(
                                snapshot,
                                normalized_id,
                            )
                        ),

                        Start=pd.NaT,
                        End=pd.NaT,

                        Status="Waiting",

                        Reason=(
                            f"{department} stage is "
                            f"'{clean_stage_status}'. "
                            "Finish time is unknown; "
                            "downstream stage may be reserved."
                        ),
                    )
                )

                dependency_unknown = True

                previous_department = department

                continue

            # ====================================================
            # OTHER UNFINISHED STATE
            # ====================================================

            assignments.append(
                self._assignment_record(
                    project,
                    department,

                    EmployeeID=normalized_id,

                    EmployeeName=(
                        self._employee_name(
                            snapshot,
                            normalized_id,
                        )
                    ),

                    Start=pd.NaT,
                    End=pd.NaT,

                    Status="Waiting",

                    Reason=(
                        f"{department} stage is "
                        f"'{clean_stage_status}' "
                        "and its finish time is unknown."
                    ),
                )
            )

            dependency_unknown = True

            previous_department = department

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
