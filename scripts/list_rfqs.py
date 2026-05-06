import pymysql

conn = pymysql.connect(
    host="localhost",
    port=3306,
    user="root",
    password="root123",
    database="s2p_matrix"
)
cur = conn.cursor()

cur.execute("SELECT id, rfq_number, title FROM rfq LIMIT 5")
rows = cur.fetchall()
for r in rows:
    print(f"ID: {r[0]}, Number: {r[1]}, Title: {r[2]}")

conn.close()
