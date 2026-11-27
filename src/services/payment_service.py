\"\"\"
Violating Payment Service.
Directly introduces 'asyncpg' driver connection, violating ADR-004.
\"\"\"

import asyncpg


class PaymentService:
    def __init__(self, dsn: str = \"postgresql://postgres:postgres@db:5432/orders\"):
        self.dsn = dsn

    async def record_payment(self, payment_id: str, amount: float):
        # DIRECT DATABASE DRIVER USAGE - ARCHITECTURAL VIOLATION
        conn = await asyncpg.connect(self.dsn)
        try:
            await conn.execute(
                \"INSERT INTO payments (id, amount, status) VALUES (\, \, \)\",
                payment_id,
                amount,
                \"COMPLETED\",
            )
        finally:
            await conn.close()
