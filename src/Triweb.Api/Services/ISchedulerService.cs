using Triweb.Api.Domain;

namespace Triweb.Api.Services;

public interface ISchedulerService
{
    Task<IReadOnlyList<Assignment>> ScheduleAsync(
        Project project,
        IReadOnlyList<Employee> employees,
        IReadOnlyList<Assignment> currentAssignments,
        IReadOnlyList<EmployeeLeave> leaves);
}
