# Triweb Architecture

Triweb is split into a React client, a .NET API, and a SQL schema.

- `src/Triweb.Client`: the scheduling interface, employee profiles, and project creation modal.
- `src/Triweb.Api`: REST endpoints for employees, projects, and planning assignments.
- `database/schema.sql`: the SQL Server-style relational model for production persistence.

The current scheduler is `HeuristicSchedulerService`. It is intentionally behind `ISchedulerService`, so your Jupyter Colab optimizer can replace it later through an HTTP call, a Python worker, or an exported model without changing the frontend.
