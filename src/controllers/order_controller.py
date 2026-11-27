import psycopg2

def get_orders_raw():
    # Deliberate architectural violation: bypassing repository
    conn = psycopg2.connect("dbname=unotusk user=postgres")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders")
    return cursor.fetchall()
