using Triweb.Api.Domain;

namespace Triweb.Api.Infrastructure;

public interface IPlanningRepository
{
    IReadOnlyList<Employee> GetEmployees();
    IReadOnlyList<Project> GetProjects();
    IReadOnlyList<Assignment> GetAssignments();
    IReadOnlyList<EmployeeLeave> GetLeaves();
    Project AddProject(CreateProjectRequest request);
    void AddAssignments(IReadOnlyList<Assignment> assignments);
    EmployeeLeave AddLeave(CreateLeaveRequest request);
}
