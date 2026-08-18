import pandas as pd
import pyodbc

# =============================
# SQL CONNECTION
# =============================

conn = pyodbc.connect(
    "DRIVER={ODBC Driver 18 for SQL Server};"
    "SERVER=localhost\\SQLEXPRESS;"
    "DATABASE=TriwebDB;"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;"
)

cursor = conn.cursor()

# =============================
# LOAD CSV
# =============================

employees = pd.read_csv("data/employees.csv")

# =============================
# OPTIONAL: Empty the table
# =============================

cursor.execute("DELETE FROM Employees")
conn.commit()

# =============================
# INSERT DATA
# =============================

for _, row in employees.iterrows():

    cursor.execute("""
        INSERT INTO Employees
        (Id,
         TeamId,
         DepartmentId,
         YearsOfExperience,
         FullName,
         Role)

        VALUES (?,?,?,?,?,?)
    """,

    row["Id"],
    row["TeamId"],
    int(row["DepartmentId"]),
    int(row["YearsOfExperience"]),
    row["FullName"],
    row["Role"])

conn.commit()

print("Employees imported successfully!")

conn.close()