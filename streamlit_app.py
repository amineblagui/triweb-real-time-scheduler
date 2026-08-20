"""Triweb real-time planning console.

Run with: ./.venv/Scripts/python.exe -m streamlit run streamlit_app.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from scheduler.api import (
    AssignmentRegistrationUnavailable,
    TriwebApiError,
)

from scheduler.employees import load_employees, normalize_employee_id


from scheduler.engine import (
    SchedulerEngine,
    SchedulerSnapshot,
    snapshot_metrics,
)

from scheduler.projects import clean_status

st.set_page_config(page_title="TriwebAPS", page_icon="image.png", layout="wide", initial_sidebar_state="expanded")
st.markdown(
    """
    <style>
      .block-container {max-width: 1560px; padding-top: 1.4rem; padding-bottom: 3rem;}
      [data-testid="stMetric"] {border: 1px solid #e5e7eb; border-radius: 14px; background: #fff; padding: 12px;}
      .hero {padding: 1.35rem 1.6rem; margin-bottom: 1.2rem; border-radius: 18px; color:#fff;
             background: linear-gradient(115deg,#ff4b4b,#ff4b4b 62%,#ff4b4b);}
      .hero h1 {margin:0; font-size:2rem;} .hero p {margin:.35rem 0 0; opacity:.88;}
      .status-note {border-left:4px solid #ff4b4b; padding:.65rem .9rem; background:#f0f9ff; border-radius:7px;}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def get_engine() -> SchedulerEngine:
    return SchedulerEngine()


def heading(title: str, subtitle: str) -> None:
    st.markdown(f"<div class='hero'><h1>{title}</h1><p>{subtitle}</p></div>", unsafe_allow_html=True)


def dataframe_for_display(frame: pd.DataFrame) -> pd.DataFrame:
    """Avoid timezone and NA rendering surprises without changing scheduler state."""
    result = frame.copy()
    for column in result.columns:
        if pd.api.types.is_datetime64_any_dtype(result[column]):
            result[column] = result[column].dt.strftime("%Y-%m-%d %H:%M").fillna("")
    return result


def refresh_snapshot(engine: SchedulerEngine) -> None:
    with st.spinner("Fetching live Triweb availability and projects, then rebuilding state…"):
        st.session_state.snapshot = engine.refresh()
    st.session_state.last_action = "Live API data refreshed and all scheduler state rebuilt."


def rebuild_snapshot(engine: SchedulerEngine, snapshot: SchedulerSnapshot) -> None:
    with st.spinner("Rebuilding state from the current API snapshot…"):
        st.session_state.snapshot = engine.build_snapshot(
            employees=load_employees(engine.employee_csv),
            availability_raw=snapshot.raw_availability,
            projects_raw=snapshot.raw_projects,
        )
    st.session_state.last_action = "Current API snapshot rebuilt without another network request."


def local_assignments(
    engine: SchedulerEngine,
    snapshot: SchedulerSnapshot,
) -> pd.DataFrame:
    """
    Build the operational scheduler view.

    Priority:
        1. Live API assignment
        2. Current scheduler run
        3. Local registry assignment

    One ProjectID + Department = one current row.

    Registered assignments already confirmed by Triweb
    are not shown in the Current Scheduler Decisions table.
    """

    registry = engine.registry_assignments().copy()
    current_run = snapshot.assignments.copy()

    rows = {}

    # ==========================================================
    # 1. LIVE API = HIGHEST PRIORITY
    # ==========================================================

    for _, project in snapshot.projects.iterrows():

        project_id = str(
            project["ProjectID"]
        )

        workflow = project["Workflow"]

        if workflow is None:
            continue

        for department in workflow:

            if department == "Redaction":

                employee_id = project["RedactorID"]
                employee_name = project["Redactor"]
                status = project["RedacStatus"]

            elif department == "Graphe":

                employee_id = project["GraphistID"]
                employee_name = project["Graphist"]
                status = project["GraphStatus"]

            else:
                continue

            employee_id = normalize_employee_id(
                employee_id
            )

            # API has a real employee
            if employee_id not in (None, "0"):

                # Resolve canonical employee name
                matches = snapshot.employees[
                    snapshot.employees["EmployeeID"]
                    .apply(normalize_employee_id)
                    .eq(employee_id)
                ]

                if not matches.empty:
                    employee_name = (
                        matches.iloc[0]["EmployeeName"]
                    )

                key = (
                    project_id,
                    department,
                )

                rows[key] = {
                    "Status": "Registered",
                    "ProjectID": project_id,
                    "Department": department,
                    "EmployeeID": employee_id,
                    "EmployeeName": employee_name,
                    "Priority": project["Priority"],
                    "Start": pd.NaT,
                    "End": pd.NaT,
                    "Performance": pd.NA,
                    "Reason": (
                        "Current Triweb assignment "
                        f"({str(status).strip()})"
                    ),
                }

    # ==========================================================
    # 2. CURRENT SCHEDULER RUN
    # ==========================================================

    if not current_run.empty:

        for _, assignment in current_run.iterrows():

            project_id = str(
                assignment["ProjectID"]
            )

            department = str(
                assignment["Department"]
            )

            key = (
                project_id,
                department,
            )

            # Live API already contains an employee.
            # Never overwrite API reality.
            if key in rows:
                continue

            rows[key] = assignment.to_dict()

    # ==========================================================
    # 3. LOCAL REGISTRY
    # ==========================================================

    if not registry.empty:

        for _, assignment in registry.iterrows():

            project_id = str(
                assignment["ProjectID"]
            )

            department = str(
                assignment["Department"]
            )

            key = (
                project_id,
                department,
            )

            # API or current scheduler already has the truth.
            if key in rows:
                continue

            rows[key] = assignment.to_dict()

    # ==========================================================
    # 4. BUILD FINAL DATAFRAME
    # ==========================================================

    if not rows:
        return pd.DataFrame()

    result = pd.DataFrame(
        list(rows.values())
    )

    # ----------------------------------------------------------
    # Do NOT show already-confirmed API assignments in the
    # "Current scheduler decisions" table.
    # ----------------------------------------------------------

    if "Status" in result.columns:

        result = result[
            result["Status"]
            .astype(str)
            .str.strip()
            .str.casefold()
            .ne("registered")
        ].copy()

    return result.reset_index(
        drop=True
    )

def render_metrics(snapshot: SchedulerSnapshot, engine: SchedulerEngine) -> None:
    metrics = snapshot_metrics(snapshot, engine.registry_assignments())
    cards = st.columns(4)
    for index, (label, value) in enumerate(metrics.items()):
        cards[index % 4].metric(label, f"{value:,}")


def availability_grid(snapshot: SchedulerSnapshot, department: str = "All", employee_id: str = "All") -> pd.DataFrame:
    availability = snapshot.availability.copy()
    people = snapshot.employees[["EmployeeID", "EmployeeName", "Department"]]
    availability = availability.merge(people, on="EmployeeID", how="inner")
    if department != "All":
        availability = availability[availability["Department"].eq(department)]
    if employee_id != "All":
        availability = availability[availability["EmployeeID"].eq(employee_id)]
    availability["Availability"] = availability.apply(
        lambda row: f"AM {'✓' if row['MorningAvailable'] else 'Leave'} · PM {'✓' if row['AfternoonAvailable'] else 'Leave'}", axis=1
    )
    return availability


def render_scheduler(
    snapshot: SchedulerSnapshot,
    engine: SchedulerEngine
) -> None:

    heading(
        "Real-time scheduler",
        "Live availability, current Production workload, and auditable assignment decisions."
    )

    assignments = local_assignments(
        engine,
        snapshot
    )

    st.subheader("Current scheduler decisions")

    if assignments.empty:
        st.caption(
            "No local scheduler assignment has been calculated."
        )
    else:
        columns = [
            column
            for column in [
                "Status",
                "ProjectID",
                "Department",
                "EmployeeName",
                "Priority",
                "Start",
                "End",
                "Performance",
                "Reason",
            ]
            if column in assignments
        ]

        st.dataframe(
            dataframe_for_display(
                assignments[columns]
            ),
            use_container_width=True,
            hide_index=True
        )


def render_employees(snapshot: SchedulerSnapshot) -> None:
    heading("Employees", "Active means present in both the scoring CSV and the live availability API.")
    state_columns = ["EmployeeID", "CurrentProject", "CurrentStatus", "BusyUntil", "AvailableAt", "ProductionProjects", "QueuedProjects", "PausedProjects", "RemainingHours"]
    people = snapshot.employees.merge(snapshot.scheduler_state[state_columns], on="EmployeeID", how="left")
    department = st.selectbox("Department", ["All", "Redaction", "Graphe"])
    if department != "All":
        people = people[people["Department"].eq(department)]
    query = st.text_input("Find employee")
    if query.strip():
        people = people[people["EmployeeName"].astype(str).str.contains(query, case=False, na=False) | people["EmployeeID"].astype(str).str.contains(query, na=False)]
    columns = [column for column in ["EmployeeID", "EmployeeName", "Department", "TeamName", "SubteamName", "QualityScore", "RapidityScore", "Confidence", "CurrentProject", "CurrentStatus", "BusyUntil", "AvailableAt", "ProductionProjects", "QueuedProjects", "PausedProjects"] if column in people]
    st.dataframe(dataframe_for_display(people[columns]), use_container_width=True, hide_index=True)
    if people.empty:
        return
    selected = st.selectbox("Employee profile", people["EmployeeID"].tolist(), format_func=lambda value: f"{value} · {people.loc[people['EmployeeID'].eq(value), 'EmployeeName'].iloc[0]}")
    employee = people.loc[people["EmployeeID"].eq(selected)].iloc[0]
    profile, calendar_panel = st.columns([2, 3])
    with profile:
        st.subheader(employee["EmployeeName"])
        st.write(f"{employee['Department']} · {employee.get('TeamName', 'No team')} · {employee.get('SubteamName', 'No subteam')}")
        a, b, c = st.columns(3)
        a.metric("Quality", f"{employee['QualityScore']:.2f}")
        b.metric("Rapidity", f"{employee['RapidityScore']:.2f}")
        c.metric("Confidence", f"{employee['Confidence']:.2f}")
        st.write("**Current project:**", employee.get("CurrentProject") or "None")
        st.write("**Queued projects:**", int(employee.get("QueuedProjects", 0)))
        st.write("**Paused projects:**", int(employee.get("PausedProjects", 0)))
    with calendar_panel:
        st.subheader("Live availability calendar")
        calendar = availability_grid(snapshot, employee_id=selected).copy()
        calendar["Date"] = calendar["Date"].dt.strftime("%a %d %b")
        st.dataframe(calendar[["Date", "Availability", "morningTypeInfo", "afternoonTypeInfo", "morningNote", "afternoonNote"]], use_container_width=True, hide_index=True)
    history = snapshot.workload[snapshot.workload["EmployeeID"].eq(selected)]
    st.subheader("Current Production history")
    st.dataframe(history, use_container_width=True, hide_index=True)


def render_availability(snapshot: SchedulerSnapshot) -> None:
    heading("Leave & availability", "A live two-week employee grid; non-available half-days are highlighted as leave or unavailability.")
    department = st.selectbox("Department", ["All", "Redaction", "Graphe"], key="availability_department")
    employee_values = ["All"] + snapshot.employees["EmployeeID"].tolist()
    employee_id = st.selectbox("Employee", employee_values, key="availability_employee")
    grid = availability_grid(snapshot, department, employee_id)
    state_filter = st.selectbox("Availability state", ["All", "Any unavailable", "Fully unavailable", "Fully available"])
    if state_filter == "Any unavailable":
        grid = grid[~(grid["MorningAvailable"] & grid["AfternoonAvailable"])]
    elif state_filter == "Fully unavailable":
        grid = grid[~grid["MorningAvailable"] & ~grid["AfternoonAvailable"]]
    elif state_filter == "Fully available":
        grid = grid[grid["MorningAvailable"] & grid["AfternoonAvailable"]]
    selected_dates = st.date_input("Date range", value=(grid["Date"].min().date(), grid["Date"].max().date())) if not grid.empty else ()
    if isinstance(selected_dates, tuple) and len(selected_dates) == 2:
        grid = grid[grid["Date"].dt.date.between(selected_dates[0], selected_dates[1])]
    if grid.empty:
        st.info("No live availability entries match these filters.")
        return
    matrix = grid.pivot(index="EmployeeName", columns="Date", values="Availability")
    matrix.columns = [pd.Timestamp(column).strftime("%a %d") for column in matrix.columns]
    st.dataframe(matrix, use_container_width=True)
    today = pd.Timestamp.today().normalize()
    tomorrow = today + pd.Timedelta(days=1)
    left, right = st.columns(2)
    left.subheader("Unavailable today")
    left.dataframe(dataframe_for_display(grid[grid["Date"].eq(today) & ~(grid["MorningAvailable"] & grid["AfternoonAvailable"])][["EmployeeName", "Availability", "morningTypeInfo", "afternoonTypeInfo"]]), use_container_width=True, hide_index=True)
    right.subheader("Unavailable tomorrow")
    right.dataframe(dataframe_for_display(grid[grid["Date"].eq(tomorrow) & ~(grid["MorningAvailable"] & grid["AfternoonAvailable"])][["EmployeeName", "Availability", "morningTypeInfo", "afternoonTypeInfo"]]), use_container_width=True, hide_index=True)


def render_projects(snapshot: SchedulerSnapshot) -> None:
    heading("Projects", "The live Projects API is the source of truth. FTP projects are excluded from this operating view.")
    projects = snapshot.projects.copy()
    projects["Assignment state"] = projects.apply(
        lambda row: "Needs Redaction" if row["RedacNeedsAssignment"] else "Needs Graphe" if row["GraphNeedsAssignment"] else "Assigned / released", axis=1
    )
    department = st.selectbox("Department", ["All", "Redaction", "Graphe"], key="projects_department")
    priorities = sorted(projects["Priority"].dropna().unique().tolist())
    selected_priorities = st.multiselect("Priority", priorities, default=priorities)
    positions = sorted(projects["Position"].dropna().astype(str).unique().tolist())
    selected_positions = st.multiselect("Position", positions, default=positions)
    workflows = sorted(projects["Workflow"].dropna().map(lambda value: " → ".join(value)).unique().tolist())
    selected_workflows = st.multiselect("Workflow", workflows, default=workflows)
    project_filter = st.text_input("Search project, client, or nature")
    projects["Workflow label"] = projects["Workflow"].map(lambda value: " → ".join(value) if value is not None else "Unknown / ignored")
    view = projects[projects["Priority"].isin(selected_priorities) & projects["Position"].astype(str).isin(selected_positions) & projects["Workflow label"].isin(selected_workflows)]
    if department == "Redaction":
        view = view[view["RedacApplicable"]]
    elif department == "Graphe":
        view = view[view["GraphApplicable"]]
    if project_filter.strip():
        query = project_filter.casefold()
        view = view[view[["ProjectID", "ClientName", "Nature"]].astype(str).apply(lambda column: column.str.casefold().str.contains(query, na=False)).any(axis=1)]
    columns = ["ProjectID", "ClientName", "Nature", "Priority", "Position", "ReceptionDateParsed", "DeliveryDate", "Redactor", "Graphist", "RedacStatus", "GraphStatus", "RedacDurationSeconds", "GraphDurationSeconds", "Workflow label", "Assignment state"]
    st.dataframe(dataframe_for_display(view[[column for column in columns if column in view]]), use_container_width=True, hide_index=True)


def render_statistics(snapshot: SchedulerSnapshot, engine: SchedulerEngine) -> None:
    heading("Statistics", "Interactive workload, demand, workflow, and scheduler-decision analytics from the current live snapshot.")
    assignments = local_assignments(engine, snapshot)
    left, right = st.columns(2)
    with left:
        by_department = snapshot.employees.groupby("Department", as_index=False).size()
        st.plotly_chart(px.pie(by_department, names="Department", values="size", hole=.55, title="Active employees by department"), use_container_width=True)
        priority = snapshot.projects.groupby("Priority", as_index=False).size().sort_values("Priority")
        st.plotly_chart(px.bar(priority, x="Priority", y="size", title="Projects by priority (lower is more urgent)"), use_container_width=True)
    with right:
        workload = snapshot.scheduler_state.groupby("EmployeeName", as_index=False)["ProductionProjects"].sum().sort_values("ProductionProjects", ascending=False)
        st.plotly_chart(px.bar(workload, x="ProductionProjects", y="EmployeeName", orientation="h", title="Current Production projects by employee").update_yaxes(autorange="reversed"), use_container_width=True)
        workflow = snapshot.projects.assign(Workflow=snapshot.projects["Workflow"].map(lambda value: " → ".join(value) if value is not None else "Unknown / ignored")).groupby("Workflow", as_index=False).size()
        st.plotly_chart(px.bar(workflow, x="size", y="Workflow", orientation="h", title="Projects by workflow").update_yaxes(autorange="reversed"), use_container_width=True)
    if not assignments.empty:
        st.subheader("Scheduler decisions")
        chartable = assignments[assignments["Status"].isin(["Calculated", "Pending registration", "Registered"])].copy()
        if not chartable.empty:
            st.plotly_chart(px.bar(chartable.groupby(["Department", "Status"], as_index=False).size(), x="Department", y="size", color="Status", barmode="group", title="Assignments by department and state"), use_container_width=True)
            st.metric("Average selected performance", f"{pd.to_numeric(chartable['Performance'], errors='coerce').mean():.2f}")


def render_audit(snapshot: SchedulerSnapshot, engine: SchedulerEngine) -> None:
    heading("Audit & registration", "Every calculated decision is retained locally until Triweb confirms it through an official assignment endpoint.")
    registry = engine.registry_assignments()
    if registry.empty:
        st.info("No calculated assignments are awaiting registration.")
    else:
        st.dataframe(dataframe_for_display(registry), use_container_width=True, hide_index=True)
    st.markdown("<div class='status-note'><strong>Registration is safely disabled.</strong> The supplied APIs do not document a write endpoint or request payload. No assignment is sent until an official Triweb contract is configured.</div>", unsafe_allow_html=True)


engine = get_engine()
if "snapshot" not in st.session_state:
    st.session_state.snapshot = None
if "last_action" not in st.session_state:
    st.session_state.last_action = ""

with st.sidebar:
    st.image("logo.png", width=200)
    st.title("Triweb Planning")
    st.caption("Real-time scheduler")
    page = st.radio("Navigation", ["Scheduler", "Employees", "Availability", "Projects", "Statistics", "Audit & registration"], label_visibility="collapsed")
    st.divider()
    if st.button("Refresh APIs", type="primary", use_container_width=True):
        try:
            refresh_snapshot(engine)
        except (TriwebApiError, ValueError, OSError) as exc:
            st.error(str(exc))
    if st.button("Rebuild State", use_container_width=True, disabled=st.session_state.snapshot is None):
        try:
            rebuild_snapshot(engine, st.session_state.snapshot)
        except (ValueError, OSError) as exc:
            st.error(str(exc))
    if st.button("Run Scheduler", use_container_width=True, disabled=st.session_state.snapshot is None):
        with st.spinner("Calculating feasible, non-destructive assignments…"):
            st.session_state.snapshot = engine.run_scheduler(st.session_state.snapshot)
        st.session_state.last_action = "Scheduler run completed. Calculated assignments remain pending registration."
    if st.button("Register Assignments", use_container_width=True, disabled=st.session_state.snapshot is None):
        try:
            engine.register_pending_assignments()
        except AssignmentRegistrationUnavailable as exc:
            st.warning(str(exc))
    st.divider()
    st.caption(f"Employee CSV: {engine.employee_csv}")

snapshot = st.session_state.snapshot
if snapshot is None:
    heading("Triweb operations planning", "Start by loading the real-time availability and projects APIs.")
    st.info("Choose **Refresh APIs**. The scheduler will then reconstruct active employees, live availability, Production workload, and the 15-day assignment pool.")
else:
    st.caption(f"Last API refresh: {snapshot.refreshed_at.astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}")
    if st.session_state.last_action:
        st.success(st.session_state.last_action)
    render_metrics(snapshot, engine)
    if page == "Scheduler":
        render_scheduler(snapshot, engine)
    elif page == "Employees":
        render_employees(snapshot)
    elif page == "Availability":
        render_availability(snapshot)
    elif page == "Projects":
        render_projects(snapshot)
    elif page == "Statistics":
        render_statistics(snapshot, engine)
    else:
        render_audit(snapshot, engine)
