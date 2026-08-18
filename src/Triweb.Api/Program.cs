using Triweb.Api.Domain;
using Triweb.Api.Infrastructure;
using Triweb.Api.Services;
using System.Text.Json.Serialization;

var builder = WebApplication.CreateBuilder(args);

builder.Services.ConfigureHttpJsonOptions(options =>
{
    options.SerializerOptions.Converters.Add(new JsonStringEnumConverter());
});

builder.Services.AddCors(options =>
{
    options.AddPolicy("client", policy =>
        policy.AllowAnyHeader()
            .AllowAnyMethod()
            .WithOrigins(
                "http://localhost:5173",
                "https://localhost:5173",
                "http://127.0.0.1:5173",
                "https://127.0.0.1:5173"));
});

builder.Services.AddSingleton<IPlanningRepository, InMemoryPlanningRepository>();
builder.Services.AddSingleton<ISchedulerService, HeuristicSchedulerService>();

var app = builder.Build();

app.UseCors("client");

app.MapGet("/", () => Results.Redirect("/api/planning"));

app.MapGet("/api/employees", (IPlanningRepository repository) =>
    Results.Ok(repository.GetEmployees()));

app.MapGet("/api/projects", (IPlanningRepository repository) =>
    Results.Ok(repository.GetProjects()));

app.MapGet("/api/leaves", (IPlanningRepository repository) =>
    Results.Ok(repository.GetLeaves()));

app.MapGet("/api/planning", (IPlanningRepository repository) =>
    Results.Ok(new PlanningResponse(
        repository.GetEmployees(),
        repository.GetProjects(),
        repository.GetAssignments(),
        repository.GetLeaves())));

app.MapPost("/api/projects", async (
    CreateProjectRequest request,
    IPlanningRepository repository,
    ISchedulerService scheduler) =>
{
    if (string.IsNullOrWhiteSpace(request.Name))
    {
        return Results.BadRequest(new { message = "Project name is required." });
    }

    if (request.Tasks.Count == 0 || request.Tasks.Any(task => string.IsNullOrWhiteSpace(task.Name)))
    {
        return Results.BadRequest(new { message = "At least one named task is required." });
    }

    if (request.Deadline < request.StartDate)
    {
        return Results.BadRequest(new { message = "Deadline must be after the start date." });
    }

    var project = repository.AddProject(request);
    var assignments = await scheduler.ScheduleAsync(
        project,
        repository.GetEmployees(),
        repository.GetAssignments(),
        repository.GetLeaves());
    repository.AddAssignments(assignments);

    return Results.Created($"/api/projects/{project.Id}", new ProjectCreatedResponse(project, assignments));
});

app.MapPost("/api/leaves", (CreateLeaveRequest request, IPlanningRepository repository) =>
{
    if (string.IsNullOrWhiteSpace(request.EmployeeId))
    {
        return Results.BadRequest(new { message = "Employee is required." });
    }

    if (request.ReturnDate <= request.StartDate)
    {
        return Results.BadRequest(new { message = "Return date must be after the start date." });
    }

    if (repository.GetEmployees().All(employee => employee.Id != request.EmployeeId))
    {
        return Results.BadRequest(new { message = "Employee does not exist." });
    }

    var leave = repository.AddLeave(request);
    return Results.Created($"/api/leaves/{leave.Id}", leave);
});
builder.Services.AddDbContext<APSDbContext>(options =>
    options.UseSqlServer(
        builder.Configuration.GetConnectionString("APSConnection")));

app.Run();
