using Triweb.Api.Domain;

namespace Triweb.Api.Infrastructure;

public sealed class InMemoryPlanningRepository : IPlanningRepository
{
    private readonly object _sync = new();
    private readonly List<Employee> _employees = SeedData.Employees();
    private readonly List<Project> _projects = SeedData.Projects();
    private readonly List<Assignment> _assignments = SeedData.Assignments();
    private readonly List<EmployeeLeave> _leaves = SeedData.Leaves();

    public IReadOnlyList<Employee> GetEmployees()
    {
        lock (_sync)
        {
            return _employees.ToList();
        }
    }

    public IReadOnlyList<Project> GetProjects()
    {
        lock (_sync)
        {
            return _projects.ToList();
        }
    }

    public IReadOnlyList<Assignment> GetAssignments()
    {
        lock (_sync)
        {
            return _assignments.ToList();
        }
    }

    public IReadOnlyList<EmployeeLeave> GetLeaves()
    {
        lock (_sync)
        {
            return _leaves.ToList();
        }
    }

    public Project AddProject(CreateProjectRequest request)
    {
        lock (_sync)
        {
            var projectNumber = _projects.Count + 1;
            var projectId = $"P{projectNumber:000}";
            var tasks = request.Tasks.Select((task, index) =>
                new ProjectTask(
                    $"{projectId}-T{index + 1:00}",
                    task.Name.Trim(),
                    task.Department,
                    Math.Max(1, task.EstimatedDays))).ToList();

            var project = new Project(projectId, request.Name.Trim(), request.StartDate, request.Deadline, tasks);
            _projects.Add(project);
            return project;
        }
    }

    public void AddAssignments(IReadOnlyList<Assignment> assignments)
    {
        lock (_sync)
        {
            _assignments.AddRange(assignments);
        }
    }

    public EmployeeLeave AddLeave(CreateLeaveRequest request)
    {
        lock (_sync)
        {
            var leave = new EmployeeLeave(
                $"L{_leaves.Count + 1:000}",
                request.EmployeeId,
                request.Type,
                request.StartDate,
                request.ReturnDate,
                request.Notes.Trim());

            _leaves.Add(leave);
            return leave;
        }
    }
}
