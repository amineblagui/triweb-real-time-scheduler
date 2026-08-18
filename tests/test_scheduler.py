from __future__ import annotations

import pandas as pd

from scheduler.availability import AvailabilityCalendar, prepare_availability
from scheduler.employees import build_active_employees, normalize_employee_id
from scheduler.engine import SchedulerEngine, rank_candidates


def employees() -> pd.DataFrame:
    return pd.DataFrame([
        {"EmployeeID": "438", "EmployeeName": "Red One", "Department": "Redaction", "QualityScore": 80, "RapidityScore": 80, "Confidence": 0.8},
        {"EmployeeID": "500", "EmployeeName": "Graph One", "Department": "Graphe", "QualityScore": 90, "RapidityScore": 90, "Confidence": 0.9},
        {"EmployeeID": "501", "EmployeeName": "Graph Two", "Department": "Graphe", "QualityScore": 60, "RapidityScore": 60, "Confidence": 0.6},
        {"EmployeeID": "999", "EmployeeName": "Former Employee", "Department": "Redaction", "QualityScore": 100, "RapidityScore": 100, "Confidence": 1.0},
    ])


def availability(ids=("438", "500", "501"), unavailable: set[tuple[str, str, str]] | None = None) -> list[dict]:
    unavailable = unavailable or set()
    records = []
    for employee_id in ids:
        for day in pd.bdate_range("2026-08-17", "2026-08-28"):
            date = day.strftime("%Y-%m-%d")
            records.append({
                "userId": employee_id, "workDateIso": f"{date}T00:00:00",
                "morningStatus": "leave_full" if (employee_id, date, "AM") in unavailable else "available",
                "afternoonStatus": "leave_full" if (employee_id, date, "PM") in unavailable else "available",
                "morningTypeInfo": None, "afternoonTypeInfo": None,
            })
    return records


def project(project_id="100", nature="Création du logo", redactor=None, graphist=0, redac_status=None, graph_status="En instance", position="Production", priority=1) -> dict:
    return {
        "id": project_id, "position": position, "pages": 1, "dateLivraisonPrevue": "25/08", "dateLivraison": "25/08",
        "dateReception": "18/08", "nYear": 2026, "nMonth": 8, "folderType": "Test", "priorite": priority,
        "codeClient": "C1", "raisonSociale": "Client One", "nature": nature,
        "redacteur": None, "idRedacteur": redactor, "graphiste": None, "idGraphiste": graphist,
        "etatR": redac_status, "etatG": graph_status, "dureeR": 0, "dureeG": 0,
    }


def engine(tmp_path) -> SchedulerEngine:
    return SchedulerEngine(employee_csv=tmp_path / "unused.csv", registry_file=tmp_path / "registry.json")


def snapshot(tmp_path, projects, availability_records=None):
    return engine(tmp_path).build_snapshot(employees(), availability_records or availability(), projects, planning_start=pd.Timestamp("2026-08-18 08:30"))


def test_normalize_employee_id_and_active_pool() -> None:
    assert {normalize_employee_id(value) for value in (438, 438.0, "438", " 438 ")} == {"438"}
    active = build_active_employees(employees(), prepare_availability(availability()))
    assert set(active["EmployeeID"]) == {"438", "500", "501"}


def test_live_leave_shifts_start_and_complete_task_requires_available_horizon(tmp_path) -> None:
    raw = availability(unavailable={("500", "2026-08-18", "AM"), ("500", "2026-08-18", "PM")})
    plan = snapshot(tmp_path, [project()], raw)
    result = engine(tmp_path).run_scheduler(plan, pd.Timestamp("2026-08-18 08:30")).assignments
    assigned = result[result["Status"].eq("Calculated")].iloc[0]
    assert assigned["Start"].date() == pd.Timestamp("2026-08-19").date()
    calendar = AvailabilityCalendar(prepare_availability(raw), {"438", "500", "501"})
    can_finish, *_ = calendar.task_schedule("500", pd.Timestamp("2026-08-18 08:30"), 100.0)
    assert not can_finish


def test_current_project_and_queued_project_block_candidates(tmp_path) -> None:
    current = project("current", "Création du logo", graphist=500, graph_status="En cours")
    queued = project("queued", "Création du logo", graphist=501, graph_status="Affecté")
    target = project("target")
    plan = snapshot(tmp_path, [current, queued, target])
    state = plan.scheduler_state.set_index("EmployeeID")
    assert state.loc["500", "CurrentProject"] == "current"
    assert state.loc["501", "QueuedProjects"] == 1
    result = engine(tmp_path).run_scheduler(plan, pd.Timestamp("2026-08-18 08:30")).assignments
    target_result = result[result["ProjectID"].eq("target")].iloc[0]
    assert target_result["Status"] == "Waiting"
    assert "No feasible" in target_result["Reason"]


def test_workflow_order_and_priority_ranking(tmp_path) -> None:
    two_stage = project("workflow", "Rédactionnel / création site Webtool", redactor=0, graphist=0, redac_status="En instance", graph_status="En instance", priority=1)
    plan = snapshot(tmp_path, [two_stage])
    result = engine(tmp_path).run_scheduler(plan, pd.Timestamp("2026-08-18 08:30")).assignments
    redaction = result[result["Department"].eq("Redaction")].iloc[0]
    graph = result[result["Department"].eq("Graphe")].iloc[0]
    assert redaction["Status"] == graph["Status"] == "Calculated"
    assert graph["Start"] >= redaction["End"]
    candidates = pd.DataFrame([
        {"EmployeeID": "2", "QualityScore": 100, "RapidityScore": 0, "Confidence": 0, "QueuedProjects": 0, "PausedProjects": 0, "Start": pd.Timestamp("2026-08-18 08:30")},
        {"EmployeeID": "1", "QualityScore": 60, "RapidityScore": 100, "Confidence": 100, "QueuedProjects": 0, "PausedProjects": 0, "Start": pd.Timestamp("2026-08-18 08:30")},
    ])
    assert rank_candidates(candidates, priority=1).iloc[0]["EmployeeID"] == "1"
    assert rank_candidates(candidates, priority=9).iloc[0]["EmployeeID"] == "2"


def test_local_registry_prevents_duplicate_assignment(tmp_path) -> None:
    first_engine = engine(tmp_path)
    first = first_engine.build_snapshot(employees(), availability(), [project()], planning_start=pd.Timestamp("2026-08-18 08:30"))
    first_results = first_engine.run_scheduler(first, pd.Timestamp("2026-08-18 08:30")).assignments
    assert len(first_results[first_results["Status"].eq("Calculated")]) == 1
    second_engine = engine(tmp_path)
    second = second_engine.build_snapshot(employees(), availability(), [project()], planning_start=pd.Timestamp("2026-08-18 08:30"))
    second_results = second_engine.run_scheduler(second, pd.Timestamp("2026-08-18 08:30")).assignments
    assert len(second_results[second_results["Status"].eq("Calculated")]) == 0
    assert "already exists" in second_results.iloc[0]["Reason"]
