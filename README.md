<<<<<<< ours
# Triweb Advanced Planning and Scheduling

Triweb is a React + .NET starter application for employee planning and automatic project scheduling.

## What is included

- Employee profiles with id, team id, department, role, and years of experience.
- Project creation modal with project name, required tasks, start date, and deadline.
- Schedule calendar showing which employee is assigned to each project task by day.
- .NET scheduler service interface ready to connect to your Jupyter Colab optimizer.
- Planned employee leave and vacation page with start date and return date.
- SQL schema in `database/schema.sql` for the production database model.
- CSV import notes and scheduler integration guide in `docs/scheduler-and-data.md`.

## Run in VS Code

Open this folder in VS Code, then use two terminals:

```powershell
dotnet run --project src\Triweb.Api\Triweb.Api.csproj
```

```powershell
cd src\Triweb.Client
npm.cmd run dev
```

Open `http://127.0.0.1:5173`.

## Future scheduler integration

Replace `HeuristicSchedulerService` in `src/Triweb.Api/Services` with a service that calls your Colab scheduler, a Python API, or an exported model. The frontend already posts projects to `POST /api/projects` and refreshes the planning board from `GET /api/planning`.

Put CSV files in `data/` and notebooks in `notebooks/`. See `docs/scheduler-and-data.md` for the recommended file columns, SQL import script, and the clean way to turn `V4_Scheduler.ipynb` into a scheduler service.
=======
# Triweb real-time scheduler

An operational Streamlit scheduler for Triweb Redaction and Graphe work. The business rules live in reusable Python modules, so the same implementation runs from Streamlit, Jupyter, and the test suite.

## Run

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run streamlit_app.py
```

The app reads the supplied historical employee score file from `C:\Users\amine\medimar\employees.csv` by default. Set `TRIWEB_EMPLOYEES_CSV` to use another location:

```powershell
$env:TRIWEB_EMPLOYEES_CSV = "C:\path\to\employees.csv"
```

Projects and daily availability are always read live from the documented Triweb APIs. They are never replaced with the sample CSV project data in this repository.

## What is enforced

- Employee IDs are normalized once and an active employee must occur in both the CSV and the availability API.
- Only the final, verified `Untitled6.ipynb` nature/workflow and duration maps are used; FTP and unknown work are not scheduled.
- Existing Production `En cours`, `Affecté`, and `En pause` stages reconstruct current, queued, paused, and remaining employee work from the live API.
- Candidates must have no current project and no queued project before ranking.
- Scheduling respects work periods, weekends, live half-day availability, the API horizon, post-task breaks, the 38-hour ISO-week ceiling, priority, and the Redaction → Graphe dependency.
- `data/assignment_registry.json` makes calculations idempotent using `ProjectID + Department`; the API snapshot reconciles entries once Triweb confirms an assignee.

## Registration safety

The two supplied endpoints are read endpoints. Their `OPTIONS` requests are authenticated and do not disclose a public assignment-write contract. The app therefore displays pending registration and audit data but deliberately sends no guessed `POST`, `PUT`, or payload. Implement an official adapter in `scheduler/api.py` only after Triweb provides the endpoint, authentication, and exact request schema.

## Notebook and tests

Open [notebooks/Triweb_RealTime_Scheduler.ipynb](notebooks/Triweb_RealTime_Scheduler.ipynb) for an executable live development flow using the same modules as Streamlit.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```
>>>>>>> theirs
