"""Quick verification of LL87 data in Supabase"""
import psycopg2

DB_HOST = "aws-0-us-west-2.pooler.supabase.com"
DB_PORT = "5432"
DB_NAME = "postgres"
DB_USER = "postgres.lhtuvtfqjovfuwuxckcw"
DB_PASSWORD = "U4Y$A9$x1GBRooAF"

conn = psycopg2.connect(
    host=DB_HOST,
    port=DB_PORT,
    dbname=DB_NAME,
    user=DB_USER,
    password=DB_PASSWORD,
    sslmode="require"
)

cur = conn.cursor()

print("\n=== LL87 Data Summary ===")
cur.execute("""
    SELECT reporting_period, COUNT(*), COUNT(DISTINCT bbl)
    FROM ll87_raw
    GROUP BY reporting_period
    ORDER BY reporting_period
""")

print("\nPeriod       | Total Rows | Unique BBLs")
print("-" * 45)
for row in cur.fetchall():
    print(f"{row[0]:12} | {row[1]:10} | {row[2]:11}")

print("\n=== Sample Record from Each Period ===")
cur.execute("""
    SELECT DISTINCT ON (reporting_period)
        reporting_period,
        bbl,
        audit_template_id,
        raw_data->>'Submittal Information_Building Information_Address' as address_2012
    FROM ll87_raw
    WHERE reporting_period = '2012-2018'
    ORDER BY reporting_period, bbl
    LIMIT 1
""")
row = cur.fetchone()
if row:
    print(f"\n2012-2018 Sample:")
    print(f"  BBL: {row[1]}")
    print(f"  Address: {row[3]}")

cur.execute("""
    SELECT DISTINCT ON (reporting_period)
        reporting_period,
        bbl,
        audit_template_id,
        raw_data->>'Property Name' as name,
        raw_data->>'Building Street Address' as address_2019
    FROM ll87_raw
    WHERE reporting_period = '2019-2024'
    ORDER BY reporting_period, bbl
    LIMIT 1
""")
row = cur.fetchone()
if row:
    print(f"\n2019-2024 Sample:")
    print(f"  BBL: {row[1]}")
    print(f"  Name: {row[3]}")
    print(f"  Address: {row[4]}")

conn.close()
print("\nVerification complete!")
