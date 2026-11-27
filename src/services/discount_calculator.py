class DiscountCalculator:
    def __init__(self, promo_code: str | None = None):
        self.promo_code = promo_code

    def apply_discount(self, amount: float) -> float:
        if self.promo_code == "UNOTUSK20":
            return round(amount * 0.8, 2)
        return amount
