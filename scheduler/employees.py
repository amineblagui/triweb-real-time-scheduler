"""Employee loading, normalization, and active-pool rules."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pandas as pd

from .config import SCHEDULABLE_DEPARTMENTS


class EmployeeDataError(ValueError):
    """The supplied static employee data cannot support scheduling."""


def normalized_text(value: object) -> str:
    """Accent-insensitive normal form used for notebook business labels."""
    if pd.isna(value):
        return ""
    value = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", value.lower().replace(">", " greater than ")).strip()


def normalize_employee_id(value: object) -> str | None:
    """Normalize 438, 438.0, '438', and ' 438 ' to the same key."""
    if pd.isna(value):
        return None
    try:
        number = float(value)
        if number.is_integer():
            return str(int(number))
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text or None


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise EmployeeDataError(
            f"Employee CSV not found at {path}. Set TRIWEB_EMPLOYEES_CSV to the supplied employees.csv path."
        )
    try:
        return pd.read_csv(path, sep=";", encoding="utf-8-sig")
    except UnicodeDecodeError:
        return pd.read_csv(path, sep=";", encoding="latin-1")


def load_employees(path: Path) -> pd.DataFrame:
    """Load the supplied historical employee scoring file into one schema."""
    employees = _read_csv(path).rename(
        columns={
            "id": "EmployeeID",
            "empname": "EmployeeName",
            "departement": "Department",
            "team_name": "TeamName",
            "subteam_name": "SubteamName",
        }
    ).copy()
    required = {"EmployeeID", "EmployeeName", "Department", "QualityScore", "RapidityScore", "Confidence"}
    missing = sorted(required - set(employees.columns))
    if missing:
        raise EmployeeDataError(f"Employee CSV is missing required scheduler columns: {', '.join(missing)}.")
    employees["EmployeeID"] = employees["EmployeeID"].map(normalize_employee_id)
    employees = employees[employees["EmployeeID"].notna()].copy()
    if employees["EmployeeID"].duplicated().any():
        duplicate_ids = ", ".join(employees.loc[employees["EmployeeID"].duplicated(), "EmployeeID"].head(5))
        raise EmployeeDataError(f"Employee CSV has duplicate normalized IDs: {duplicate_ids}.")
    employees["Department"] = employees["Department"].astype(str).str.strip()
    for column in ("QualityScore", "RapidityScore", "Confidence"):
        employees[column] = pd.to_numeric(employees[column], errors="coerce")
    for optional in ("TeamName", "SubteamName"):
        if optional not in employees:
            employees[optional] = pd.NA
    return employees.reset_index(drop=True)


def build_active_employees(employees: pd.DataFrame, availability: pd.DataFrame) -> pd.DataFrame:
    """Keep only CSV employees that occur in the live availability API."""
    if "userId" not in availability:
        raise EmployeeDataError("Availability API is missing userId; active employee pool cannot be built.")
    availability_ids = set(availability["userId"].map(normalize_employee_id).dropna())
    active = employees[employees["EmployeeID"].isin(availability_ids)].copy()
    active = active[active["Department"].isin(SCHEDULABLE_DEPARTMENTS)].copy()
    return active.sort_values(["Department", "EmployeeName"]).reset_index(drop=True)
