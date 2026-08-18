using Microsoft.EntityFrameworkCore;
using Triweb.Api.Models;

namespace Triweb.Api.Data;

public class APSDbContext : DbContext
{
    public APSDbContext(DbContextOptions<APSDbContext> options)
        : base(options)
    {
    }

    public DbSet<Employee> Employees => Set<Employee>();

    public DbSet<Project> Projects => Set<Project>();

    public DbSet<ProjectTask> ProjectTasks => Set<ProjectTask>();

    public DbSet<EmployeeLeave> EmployeeLeaves => Set<EmployeeLeave>();

    public DbSet<EmployeeHistory> EmployeeHistory => Set<EmployeeHistory>();

    public DbSet<Planning> Planning => Set<Planning>();

    public DbSet<Team> Teams => Set<Team>();

    public DbSet<Department> Departments => Set<Department>();

    public DbSet<SchedulerEvent> SchedulerEvents => Set<SchedulerEvent>();
}