import psycopg2
import os

DATABASE_PUBLIC_URL = os.getenv("DATABASE_PUBLIC_URL")

try:
    conn = psycopg2.connect(DATABASE_PUBLIC_URL)
    print("Connected to the database successfully!")

    cursor = conn.cursor()
    schema_path = "database/schema.sql"
    with open(schema_path, "r") as f:
        print("Executing schema.sql...")
        try:

            cursor.execute(f.read())
            conn.commit()
        except psycopg2.Error as e:
            print("Error executing schema.sql:", e)
            conn.rollback()

    cursor.close()
    conn.close()
except psycopg2.Error as e:
    print("Error connecting to PostgreSQL:", e)
