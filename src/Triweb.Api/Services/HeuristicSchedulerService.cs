using Triweb.Api.Domain;

namespace Triweb.Api.Services;

public sealed class HeuristicSchedulerService : ISchedulerService
{
    private static readonly string[] Palette =
    [
        "#5b6cff",
        "#f05a47",
        "#00b894",
        "#9b5cff",
        "#ff9f43",
        "#00c2d7",
        "#ff5c8a",
        "#9bdc65",
        "#f45be8",
        "#ffc83d"
    ];

    public Task<IReadOnlyList<Assignment>> ScheduleAsync(
        Project project,
        IReadOnlyList<Employee> employees,
        IReadOnlyList<Assignment> currentAssignments,
        IReadOnlyList<EmployeeLeave> leaves)
    {
        var color = Palette[Math.Abs(project.Id.GetHashCode()) % Palette.Length];
        var assignments = new List<Assignment>();
        var taskCursor = project.StartDate;

        foreach (var task in project.Tasks)
        {
            var eligibleEmployees = employees
                .Where(employee => employee.Department == task.Department)
                .OrderByDescending(employee => employee.YearsOfExperience)
                .ToList();

            var selected = eligibleEmployees
                .Select(employee => new
                {
                    Employee = employee,
                    Start = NextAvailableDate(employee.Id, taskCursor, currentAssignments.Concat(assignments), leaves)
                })
                .OrderBy(candidate => candidate.Start)
                .ThenByDescending(candidate => candidate.Employee.YearsOfExperience)
                .First();

            var start = selected.Start > project.Deadline ? taskCursor : selected.Start;
            var end = AddAvailableBusinessDays(start, task.EstimatedDays - 1, selected.Employee.Id, leaves);

            if (end > project.Deadline)
            {
                end = project.Deadline;
            }

            assignments.Add(new Assignment(
                $"A-{project.Id}-{task.Id}",
                project.Id,
                task.Id,
                selected.Employee.Id,
                start,
                end,
                color));

            taskCursor = AddBusinessDays(end, 1);
        }

        return Task.FromResult<IReadOnlyList<Assignment>>(assignments);
    }

    private static DateOnly NextAvailableDate(
        string employeeId,
        DateOnly desiredStart,
        IEnumerable<Assignment> assignments,
        IReadOnlyList<EmployeeLeave> leaves)
    {
        var cursor = desiredStart;

        while (IsAssigned(employeeId, cursor, assignments) || IsOnLeave(employeeId, cursor, leaves) || IsWeekend(cursor))
        {
            cursor = AddBusinessDays(cursor, 1);
        }

        return cursor;
    }

    private static DateOnly AddAvailableBusinessDays(
        DateOnly date,
        int days,
        string employeeId,
        IReadOnlyList<EmployeeLeave> leaves)
    {
        var remaining = days;
        var cursor = date;

        while (remaining > 0)
        {
            cursor = cursor.AddDays(1);

            if (!IsWeekend(cursor) && !IsOnLeave(employeeId, cursor, leaves))
            {
                remaining--;
            }
        }

        return cursor;
    }

    private static bool IsAssigned(string employeeId, DateOnly date, IEnumerable<Assignment> assignments) =>
        assignments.Any(assignment =>
            assignment.EmployeeId == employeeId &&
            assignment.StartDate <= date &&
            assignment.EndDate >= date);

    private static bool IsOnLeave(string employeeId, DateOnly date, IReadOnlyList<EmployeeLeave> leaves) =>
        leaves.Any(leave =>
            leave.EmployeeId == employeeId &&
            leave.StartDate <= date &&
            leave.ReturnDate > date);

    private static bool IsWeekend(DateOnly date) =>
        date.DayOfWeek is DayOfWeek.Saturday or DayOfWeek.Sunday;

    private static DateOnly AddBusinessDays(DateOnly date, int days)
    {
        var direction = days < 0 ? -1 : 1;
        var remaining = Math.Abs(days);
        var cursor = date;

        while (remaining > 0)
        {
            cursor = cursor.AddDays(direction);

            if (!IsWeekend(cursor))
            {
                remaining--;
            }
        }

        return cursor;
    }
}
