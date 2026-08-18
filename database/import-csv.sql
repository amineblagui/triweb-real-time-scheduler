-- SQL Server examples. Adjust paths to match your machine.
-- Recommended folder in this project: C:\Users\amine\Documents\triwebaps\data

BULK INSERT Employees
FROM 'C:\Users\amine\Documents\triwebaps\data\employees.csv'
WITH (
    FORMAT = 'CSV',
    FIRSTROW = 2,
    FIELDQUOTE = '"',
    FIELDTERMINATOR = ',',
    ROWTERMINATOR = '0x0a',
    TABLOCK
);

BULK INSERT EmployeeHistory
FROM 'C:\Users\amine\Documents\triwebaps\data\employee_history_v2.csv'
WITH (
    FORMAT = 'CSV',
    FIRSTROW = 2,
    FIELDQUOTE = '"',
    FIELDTERMINATOR = ',',
    ROWTERMINATOR = '0x0a',
    TABLOCK
);

BULK INSERT Projects
FROM 'C:\Users\amine\Documents\triwebaps\data\projects.csv'
WITH (
    FORMAT = 'CSV',
    FIRSTROW = 2,
    FIELDQUOTE = '"',
    FIELDTERMINATOR = ',',
    ROWTERMINATOR = '0x0a',
    TABLOCK
);

BULK INSERT ProjectTasks
FROM 'C:\Users\amine\Documents\triwebaps\data\project_tasks.csv'
WITH (
    FORMAT = 'CSV',
    FIRSTROW = 2,
    FIELDQUOTE = '"',
    FIELDTERMINATOR = ',',
    ROWTERMINATOR = '0x0a',
    TABLOCK
);
BULK INSERT EmployeeLeaves
From 'C:\Users\amine\Documents\triwebaps\data\employee_leaves.csv'
WITH (
    FORMAT = 'CSV',
    FIRSTROW = 2,
    FIELDQUOTE = '"',
    FIELDTERMINATOR = ',',
    ROWTERMINATOR = '0x0a',
    TABLOCK
);