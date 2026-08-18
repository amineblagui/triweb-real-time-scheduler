"""Triweb project normalization and the notebook's project business rules."""

from __future__ import annotations

from typing import Literal

import pandas as pd

from .config import MAX_RECEPTION_AGE_DAYS, NATURE_DURATION_HOURS, NATURE_WORKFLOW, STAGE_EFFORT_SPLIT
from .employees import normalized_text, normalize_employee_id


class ProjectDataError(ValueError):
    """The live project payload is incomplete for the scheduler."""


FINISHED_STAGE_STATUSES = {"validé", "cq client", "retour cq", "retour cq traité", "finalisé"}
AVAILABLE_POSITIONS = {"client", "cq client", "retour cq"}
ACTIVE_WORK_STATUSES = {"en cours", "affecté", "en pause"}

PROJECT_COLUMNS = {
    "id": "ProjectID", "pq": "PQ", "position": "Position", "pages": "Pages",
    "dateLivraisonPrevue": "DeliveryDate", "dateLivraison": "DeliveredDate",
    "dateReception": "ReceptionDate", "folderType": "FolderType", "priorite": "Priority",
    "codeClient": "ClientCode", "raisonSociale": "ClientName", "nature": "Nature",
    "redacteur": "Redactor", "idRedacteur": "RedactorID", "graphiste": "Graphist",
    "idGraphiste": "GraphistID", "etatR": "RedacStatus", "etatG": "GraphStatus",
    "dureeR": "RedacDurationSeconds", "dureeG": "GraphDurationSeconds",
}


def clean_status(value: object) -> str:
    return "" if pd.isna(value) else str(value).strip().casefold()


def clean_position(value: object) -> str:
    return "" if pd.isna(value) else str(value).strip().casefold()


def workflow_from_nature(nature: object) -> tuple[str, ...] | None:
    key = normalized_text(nature)
    for configured, workflow in NATURE_WORKFLOW.items():
        if normalized_text(configured) == key:
            return workflow
    return None


def expected_total_duration(nature: object) -> float | None:
    key = normalized_text(nature)
    for configured, hours in NATURE_DURATION_HOURS.items():
        if normalized_text(configured) == key:
            return hours
    return None


def stage_expected_hours(nature: object, department: str) -> float | None:
    total = expected_total_duration(nature)
    workflow = workflow_from_nature(nature)
    if total is None or workflow is None or department not in workflow:
        return None
    return total if len(workflow) == 1 else total * STAGE_EFFORT_SPLIT[department]


def remaining_stage_hours(nature: object, department: str, worked_seconds: object) -> float | None:
    expected = stage_expected_hours(nature, department)
    if expected is None:
        return None
    worked = pd.to_numeric(worked_seconds, errors="coerce")
    return max(0.0, expected - (0.0 if pd.isna(worked) else float(worked) / 3600.0))


def prepare_projects(raw_projects: list[dict] | pd.DataFrame, today: pd.Timestamp | None = None) -> pd.DataFrame:
    projects = pd.DataFrame(raw_projects).rename(columns=PROJECT_COLUMNS).copy()
    required = {"ProjectID", "Position", "ReceptionDate", "Priority", "Nature", "RedactorID", "GraphistID", "RedacStatus", "GraphStatus", "RedacDurationSeconds", "GraphDurationSeconds", "nYear"}
    missing = sorted(required - set(projects.columns))
    if missing:
        raise ProjectDataError(f"Projects API is missing required scheduler fields: {', '.join(missing)}.")
    projects = projects.loc[:, ~projects.columns.duplicated()].copy()
    projects = projects[projects["Position"].map(clean_position).ne("ftp")].copy()
    projects["ProjectID"] = projects["ProjectID"].astype(str)
    projects["Priority"] = pd.to_numeric(projects["Priority"], errors="coerce")
    projects["Workflow"] = projects["Nature"].map(workflow_from_nature)
    projects["ExpectedTotalHours"] = projects["Nature"].map(expected_total_duration)
    projects["RedacApplicable"] = projects["Workflow"].map(lambda value: value is not None and "Redaction" in value)
    projects["GraphApplicable"] = projects["Workflow"].map(lambda value: value is not None and "Graphe" in value)
    projects["RedacNeedsAssignment"] = projects["RedacApplicable"] & pd.to_numeric(projects["RedactorID"], errors="coerce").eq(0)
    projects["GraphNeedsAssignment"] = projects["GraphApplicable"] & pd.to_numeric(projects["GraphistID"], errors="coerce").eq(0)
    reception = projects["ReceptionDate"].astype(str).str.strip() + "/" + pd.to_numeric(projects["nYear"], errors="coerce").astype("Int64").astype(str)
    projects["ReceptionDateParsed"] = pd.to_datetime(reception, format="%d/%m/%Y", errors="coerce")
    reference = pd.Timestamp.today().normalize() if today is None else pd.Timestamp(today).normalize()
    projects["ReceptionAgeDays"] = (reference - projects["ReceptionDateParsed"]).dt.days
    projects["RecentEnough"] = projects["ReceptionDateParsed"].notna() & projects["ReceptionAgeDays"].between(0, MAX_RECEPTION_AGE_DAYS, inclusive="both")
    return projects.reset_index(drop=True)


def scheduler_pool(projects: pd.DataFrame) -> pd.DataFrame:
    return projects[projects["RecentEnough"] & (projects["RedacNeedsAssignment"] | projects["GraphNeedsAssignment"])].sort_values(
        ["Priority", "ReceptionDateParsed", "ProjectID"], na_position="last"
    ).reset_index(drop=True)


def stage_values(project: pd.Series, department: str) -> tuple[object, object, object]:
    if department == "Redaction":
        return project["RedactorID"], project["RedacStatus"], project["RedacDurationSeconds"]
    if department == "Graphe":
        return project["GraphistID"], project["GraphStatus"], project["GraphDurationSeconds"]
    raise ValueError(f"Unknown department: {department}")


def project_stage_availability(position: object, status: object, employee_id: object) -> str:
    numeric_id = pd.to_numeric(employee_id, errors="coerce")
    if pd.isna(numeric_id):
        return "NOT_APPLICABLE"
    if numeric_id == 0:
        return "NEEDS_ASSIGNMENT"
    if clean_status(status) in FINISHED_STAGE_STATUSES or clean_position(position) in AVAILABLE_POSITIONS:
        return "AVAILABLE"
    if clean_position(position) == "production":
        if clean_status(status) in {"en cours", "affecté"}:
            return "BUSY"
        if clean_status(status) == "en pause":
            return "PAUSED"
    return "UNKNOWN"


def stage_is_finished(project: pd.Series, department: str) -> bool:
    employee_id, status, _ = stage_values(project, department)
    return project_stage_availability(project["Position"], status, employee_id) in {"AVAILABLE", "NOT_APPLICABLE"}


def stage_needs_assignment(project: pd.Series, department: str) -> bool:
    employee_id, _, _ = stage_values(project, department)
    numeric_id = pd.to_numeric(employee_id, errors="coerce")
    return bool(pd.notna(numeric_id) and numeric_id == 0)


def update_local_assignment(project: pd.Series, department: str, employee_id: str) -> None:
    if department == "Redaction":
        project["RedactorID"], project["RedacStatus"] = int(employee_id), "Affecté"
    elif department == "Graphe":
        project["GraphistID"], project["GraphStatus"] = int(employee_id), "Affecté"
    else:
        raise ValueError(f"Unknown department: {department}")


def build_employee_workload(projects: pd.DataFrame, active_employee_ids: set[str]) -> pd.DataFrame:
    records: list[dict] = []
    for _, project in projects.iterrows():
        workflow = project["Workflow"]
        if workflow is None or clean_position(project["Position"]) != "production":
            continue
        for department, employee_key, status_key, duration_key in (
            ("Redaction", "RedactorID", "RedacStatus", "RedacDurationSeconds"),
            ("Graphe", "GraphistID", "GraphStatus", "GraphDurationSeconds"),
        ):
            employee_id = normalize_employee_id(project[employee_key])
            status = clean_status(project[status_key])
            if department in workflow and employee_id not in {None, "0"} and employee_id in active_employee_ids and status in ACTIVE_WORK_STATUSES:
                records.append({"EmployeeID": employee_id, "Department": department, "ProjectID": str(project["ProjectID"]), "Nature": project["Nature"], "Position": project["Position"], "Status": status, "Priority": project["Priority"], "WorkedSeconds": pd.to_numeric(project[duration_key], errors="coerce")})
    return pd.DataFrame(records, columns=["EmployeeID", "Department", "ProjectID", "Nature", "Position", "Status", "Priority", "WorkedSeconds"])
