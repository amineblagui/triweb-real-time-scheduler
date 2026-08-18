"""Durable, idempotent local assignment and audit registry."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


class AssignmentRegistry:
    """ProjectID + Department uniqueness without pretending a write API exists."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._records = self._load()

    @staticmethod
    def key(project_id: object, department: object) -> str:
        return f"{str(project_id).strip()}::{str(department).strip()}"

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Assignment registry is unreadable: {self.path}: {exc}") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("records", {}), dict):
            raise RuntimeError(f"Assignment registry has an invalid format: {self.path}")
        return payload["records"]

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"records": self._records}, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        temporary.replace(self.path)

    def has_local_assignment(self, project_id: object, department: object) -> bool:
        record = self._records.get(self.key(project_id, department))
        return record is not None and record.get("Status") in {"Calculated", "Pending registration", "Registered"}

    def record(self, assignment: dict[str, Any]) -> None:
        key = self.key(assignment["ProjectID"], assignment["Department"])
        if self.has_local_assignment(assignment["ProjectID"], assignment["Department"]):
            raise ValueError(f"Duplicate local scheduler assignment: {key}")
        saved = {**assignment, "Timestamp": datetime.now(timezone.utc).isoformat(), "Status": "Pending registration"}
        self._records[key] = saved
        self._save()

    def reconcile(self, projects: pd.DataFrame) -> None:
        """Mark local entries registered when the authoritative API confirms an ID."""
        changed = False
        for _, project in projects.iterrows():
            for department, employee_column in (("Redaction", "RedactorID"), ("Graphe", "GraphistID")):
                key = self.key(project["ProjectID"], department)
                record = self._records.get(key)
                employee_id = pd.to_numeric(project[employee_column], errors="coerce")
                if record and pd.notna(employee_id) and employee_id > 0 and record.get("Status") != "Registered":
                    record["Status"] = "Registered"
                    record["ApiConfirmedAt"] = datetime.now(timezone.utc).isoformat()
                    changed = True
        if changed:
            self._save()

    def assignments(self) -> pd.DataFrame:
        return pd.DataFrame(self._records.values())

    def pending(self) -> pd.DataFrame:
        records = self.assignments()
        if records.empty or "Status" not in records:
            return records
        return records[records["Status"].eq("Pending registration")].copy()
