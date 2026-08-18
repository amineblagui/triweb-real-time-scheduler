using Triweb.Api.Domain;

namespace Triweb.Api.Infrastructure;

public static class SeedData
{
    public static List<Employee> Employees() =>
    [
        new("E009", "T-ALPHA", Department.R, 8, "Nadia Rahal", "Senior Planner"),
        new("E026", "T-ALPHA", Department.QualityControl, 5, "Omar Bell", "Frontend Engineer"),
        new("E015", "T-BETA", Department.Graph, 6, "Lina Park", "Data Analyst"),
        new("E003", "T-BETA", Department.Graph, 9, "Maya Diaz", "Operations Lead"),
        new("E021", "T-GAMMA", Department.R, 3, "Ilyes Chen", "Backend Engineer"),
        new("E019", "T-GAMMA", Department.R, 7, "Sara Malik", "Optimization Analyst"),
        new("E002", "T-DELTA", Department.QualityControl, 4, "Adam Stone", "Project Coordinator"),
        new("E024", "T-DELTA", Department.QualityControl, 10, "Hana Ito", "Architect"),
        new("E018", "T-EPSILON", Department.R, 2, "Noah Reed", "BI Specialist"),
        new("E005", "T-EPSILON", Department.Graph, 6, "Yasmine Noor", "Delivery Manager"),
        new("E029", "T-ZETA", Department.QualityControl, 4, "Victor Lane", "Integration Engineer"),
        new("E013", "T-ZETA", Department.Graph, 5, "Amina Cole", "Forecast Analyst"),
        new("E010", "T-ETA", Department.R, 8, "Karim Vos", "Resource Manager"),
        new("E022", "T-ETA", Department.R, 6, "Elena Fox", "QA Engineer"),
        new("E011", "T-THETA", Department.Graph, 3, "Sofia Brand", "Planning Analyst")
    ];

    public static List<Project> Projects() =>
    [
        new("P001", "Capacity Model Upgrade", new DateOnly(2026, 7, 6), new DateOnly(2026, 7, 17),
        [
            new("P001-T01", "Data audit", Department.Graph, 4),
            new("P001-T02", "Scenario service", Department.R, 5),
            new("P001-T03", "Rollout plan", Department.QualityControl, 3)
        ]),
        new("P002", "Factory Line Simulation", new DateOnly(2026, 7, 9), new DateOnly(2026, 7, 28),
        [
            new("P002-T01", "Constraint mapping", Department.Graph, 5),
            new("P002-T02", "Simulation API", Department.QualityControl, 8),
            new("P002-T03", "KPI dashboard", Department.R, 4)
        ]),
        new("P003", "Shift Optimizer", new DateOnly(2026, 8, 3), new DateOnly(2026, 8, 14),
        [
            new("P003-T01", "Rules review", Department.R, 3),
            new("P003-T02", "Optimization run", Department.QualityControl, 5),
            new("P003-T03", "Calendar sync", Department.Graph, 4)
        ])
    ];

    public static List<Assignment> Assignments() =>
    [
        new("A001", "P001", "P001-T01", "E015", new DateOnly(2026, 7, 6), new DateOnly(2026, 7, 9), "#5b6cff"),
        new("A002", "P001", "P001-T02", "E009", new DateOnly(2026, 7, 10), new DateOnly(2026, 7, 15), "#5b6cff"),
        new("A003", "P001", "P001-T03", "E003", new DateOnly(2026, 7, 15), new DateOnly(2026, 7, 17), "#5b6cff"),
        new("A004", "P002", "P002-T01", "E010", new DateOnly(2026, 7, 9), new DateOnly(2026, 7, 14), "#f05a47"),
        new("A005", "P002", "P002-T02", "E024", new DateOnly(2026, 7, 15), new DateOnly(2026, 7, 24), "#f05a47"),
        new("A006", "P002", "P002-T03", "E019", new DateOnly(2026, 7, 23), new DateOnly(2026, 7, 28), "#f05a47"),
        new("A007", "P003", "P003-T01", "E005", new DateOnly(2026, 8, 3), new DateOnly(2026, 8, 5), "#00b894"),
        new("A008", "P003", "P003-T02", "E013", new DateOnly(2026, 8, 6), new DateOnly(2026, 8, 11), "#00b894"),
        new("A009", "P003", "P003-T03", "E026", new DateOnly(2026, 8, 10), new DateOnly(2026, 8, 14), "#00b894")
    ];

    public static List<EmployeeLeave> Leaves() =>
    [
        new("L001", "E009", LeaveType.Vacation, new DateOnly(2026, 8, 17), new DateOnly(2026, 8, 24), "Annual vacation"),
        new("L002", "E015", LeaveType.Training, new DateOnly(2026, 7, 27), new DateOnly(2026, 7, 31), "Optimization workshop"),
        new("L003", "E003", LeaveType.Personal, new DateOnly(2026, 8, 6), new DateOnly(2026, 8, 10), "Planned personal leave"),
        new("L004", "E024", LeaveType.Vacation, new DateOnly(2026, 8, 25), new DateOnly(2026, 9, 1), "Summer vacation"),
        new("L005", "E013", LeaveType.Medical, new DateOnly(2026, 7, 20), new DateOnly(2026, 7, 23), "Medical leave")
    ];
}
