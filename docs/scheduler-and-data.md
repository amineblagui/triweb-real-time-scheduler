# Scheduler and Data Integration

## Where to put your files

Use these project folders:

- `data/employees.csv`
- `data/employees_history.csv`
- `data/projects.csv`
- `data/project_tasks.csv`
- `notebooks/performance_score_calculator.ipynb`
- `notebooks/V4_Scheduler.ipynb`

The app will not execute notebooks directly. The clean production path is to turn notebook logic into a small Python API or a Python script that the .NET API can call.

## Recommended CSV columns

`employees.csv`

```csv
Id,TeamId,DepartmentId,YearsOfExperience,FullName,Role
E009,T-ALPHA,1,8,Nadia Rahal,Senior Planner
```

`employees_history.csv`

```csv
EmployeeId,ProjectId,TaskId,WorkDate,HoursWorked,PerformanceScore
E009,P001,P001-T02,2026-07-10,7.5,0.91
```

`projects.csv`

```csv
Id,Name,StartDate,Deadline
P001,Capacity Model Upgrade,2026-07-06,2026-07-17
```

`project_tasks.csv`

```csv
Id,ProjectId,Name,DepartmentId,EstimatedDays
P001-T01,P001,Data audit,3,4
```

Department ids:

- `1`: Engineering
- `2`: Operations
- `3`: Analytics

## How to import CSV into SQL Server

1. Create the database tables with `database/schema.sql`.
2. Put the CSV files in `data/`.
3. Edit file paths in `database/import-csv.sql` if your project path is different.
4. Run `database/import-csv.sql` in SQL Server Management Studio or Azure Data Studio.

For real production data, import into staging tables first, validate ids and dates, then insert into the final tables. That protects the app from malformed CSV rows.

## How to connect your Colab scheduler

The current .NET scheduler lives behind `ISchedulerService`.

Current placeholder:

```text
src/Triweb.Api/Services/HeuristicSchedulerService.cs
```

Replace it with a service such as `PythonSchedulerService` that sends this JSON to your scheduler:

```json
{
  "project": {},
  "employees": [],
  "currentAssignments": [],
  "leaves": [],
  "employeeHistory": []
}
```

The scheduler should return assignments shaped like:

```json
[
  {
    "projectId": "P004",
    "taskId": "P004-T01",
    "employeeId": "E003",
    "startDate": "2026-08-17",
    "endDate": "2026-08-18"
  }
]
```

Best path from Colab:

1. Move the reusable code from `V4_Scheduler.ipynb` into `scheduler_service.py`.
2. Build a small FastAPI endpoint `/schedule`.
3. Export the performance score logic from `performance_score_calculator.ipynb` into a normal Python module.
4. Call that FastAPI endpoint from a new .NET `PythonSchedulerService`.
5. Keep the notebooks as experiments, not as runtime dependencies.

The important contract is simple: .NET owns projects, employees, leaves, and saved assignments; Python receives that data, computes the schedule, and returns assignment rows.
