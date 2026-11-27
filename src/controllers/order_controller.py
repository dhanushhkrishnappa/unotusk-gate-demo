import psycopg2

def get_orders_raw():
    # Deliberate architectural violation: direct database connection
    conn = psycopg2.connect("dbname=unotusk user=postgres")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders")
    return cursor.fetchall()
