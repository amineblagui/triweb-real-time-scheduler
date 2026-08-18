-- ===========================================
-- APS DATABASE
-- ===========================================

CREATE TABLE Departments(

    DepartmentId INT PRIMARY KEY,

    DepartmentName NVARCHAR(100)

);

INSERT INTO Departments VALUES
(1,'R'),
(2,'Graphes'),
(3,'Quality_Control');
---------------------------------------------------

CREATE TABLE Teams(

    TeamId NVARCHAR(30) PRIMARY KEY,

    TeamName NVARCHAR(80) NOT NULL,

    DepartmentId INT NOT NULL,

    FOREIGN KEY (DepartmentId)
        REFERENCES Departments(DepartmentId)

);

---------------------------------------------------

CREATE TABLE Employees(
    employeeId NVARCHAR(20) PRIMARY KEY,

    FullName NVARCHAR(120) NOT NULL,

    TeamId NVARCHAR(30) NOT NULL,

    DepartmentId INT NOT NULL,

    Experience INT NOT NULL,

    Role NVARCHAR(80),

    PerformanceScore FLOAT DEFAULT 0,

    IsActive BIT DEFAULT 1,

    FOREIGN KEY (DepartmentId)
        REFERENCES Departments(DepartmentId),

    FOREIGN KEY (TeamId)
        REFERENCES Teams(TeamId)

);

---------------------------------------------------

CREATE TABLE EmployeeHistory(

    HistoryId INT IDENTITY(1,1) PRIMARY KEY,

    EmployeeId NVARCHAR(20),

    ProjectId NVARCHAR(20),

    TaskType NVARCHAR(20),

    EstimatedHours FLOAT,

    ActualHours FLOAT,

    Accuracy FLOAT,

    NumberOfReturns INT,

    PerformanceScore FLOAT,

    WorkDate DATE,

    FOREIGN KEY(EmployeeId)
        REFERENCES Employees(EmployeeId)

);

---------------------------------------------------

CREATE TABLE EmployeeLeaves(

    LeaveId INT IDENTITY(1,1) PRIMARY KEY,

    EmployeeId NVARCHAR(20),

    StartDate DATE,

    EndDate DATE,

    Notes NVARCHAR(200),

    FOREIGN KEY(EmployeeId)
        REFERENCES Employees(EmployeeId)

);

---------------------------------------------------

CREATE TABLE Projects(

    ProjectId NVARCHAR(20) PRIMARY KEY,

    Client NVARCHAR(120),

    ProjectName NVARCHAR(200),

    StartDate DATE,

    Deadline DATE,

    Status NVARCHAR(30)

);

---------------------------------------------------

CREATE TABLE ProjectTasks(

    TaskId NVARCHAR(20) PRIMARY KEY,

    ProjectId NVARCHAR(20),

    Feature NVARCHAR(150),

    WorkflowOrder INT,

    DepartmentId INT,

    EstimatedHours FLOAT,

    Priority NVARCHAR(20),

    Status NVARCHAR(30),

    FOREIGN KEY(ProjectId)
        REFERENCES Projects(ProjectId),

    FOREIGN KEY(DepartmentId)
        REFERENCES Departments(DepartmentId)

);

---------------------------------------------------

CREATE TABLE Planning(

    PlanningId INT IDENTITY(1,1) PRIMARY KEY,

    ProjectId NVARCHAR(20),

    TaskId NVARCHAR(20),

    EmployeeId NVARCHAR(20),

    BackupEmployeeId NVARCHAR(20),

    StartDate DATETIME,

    EndDate DATETIME,

    WorkedHours FLOAT,

    BreakMinutes INT,

    IsLeaveConflict BIT,

    FOREIGN KEY(ProjectId)
        REFERENCES Projects(ProjectId),

    FOREIGN KEY(TaskId)
        REFERENCES ProjectTasks(TaskId),

    FOREIGN KEY(EmployeeId)
        REFERENCES Employees(EmployeeId),

    FOREIGN KEY(BackupEmployeeId)
        REFERENCES Employees(EmployeeId)

);
CREATE TABLE SchedulerEvents(

    EventId INT IDENTITY PRIMARY KEY,

    EventDate DATETIME,

    EventType NVARCHAR(50),

    Description NVARCHAR(MAX)

);
