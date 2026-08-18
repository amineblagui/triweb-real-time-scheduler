namespace Triweb.Api.Domain;

public enum Department
{
    R,
    Graph,
    QualityControl,
}

public enum LeaveType
{
    Vacation,
    Medical,
    Personal,
    Training
}

public sealed record Employee(
    string Id,
    string TeamId,
    Department Department,
    int YearsOfExperience,
    string FullName,
    string Role);

public sealed record Project(
    string Id,
    string Name,
    DateOnly StartDate,
    DateOnly Deadline,
    IReadOnlyList<ProjectTask> Tasks);

public sealed record ProjectTask(
    string Id,
    string Name,
    Department Department,
    int EstimatedDays);

public sealed record Assignment(
    string Id,
    string ProjectId,
    string TaskId,
    string EmployeeId,
    DateOnly StartDate,
    DateOnly EndDate,
    string Color);

public sealed record EmployeeLeave(
    string Id,
    string EmployeeId,
    LeaveType Type,
    DateOnly StartDate,
    DateOnly ReturnDate,
    string Notes);

public sealed record CreateProjectRequest(
    string Name,
    DateOnly StartDate,
    DateOnly Deadline,
    IReadOnlyList<CreateTaskRequest> Tasks);

public sealed record CreateTaskRequest(
    string Name,
    Department Department,
    int EstimatedDays);

public sealed record CreateLeaveRequest(
    string EmployeeId,
    LeaveType Type,
    DateOnly StartDate,
    DateOnly ReturnDate,
    string Notes);

public sealed record PlanningResponse(
    IReadOnlyList<Employee> Employees,
    IReadOnlyList<Project> Projects,
    IReadOnlyList<Assignment> Assignments,
    IReadOnlyList<EmployeeLeave> Leaves);

public sealed record ProjectCreatedResponse(Project Project, IReadOnlyList<Assignment> Assignments);
