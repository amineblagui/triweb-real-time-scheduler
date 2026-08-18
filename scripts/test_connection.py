import pyodbc

conn = pyodbc.connect(

    "DRIVER={ODBC Driver 18 for SQL Server};"

    "SERVER=localhost\\SQLEXPRESS;"

    "DATABASE=TriwebDB;"

    "Trusted_Connection=yes;"

    "TrustServerCertificate=yes;"

)

print("Connected successfully!")

conn.close()