class PricingCalculator:
    def __init__(self, tax_rate: float = 0.08):
        self.tax_rate = tax_rate

    def compute_total(self, subtotal: float) -> float:
        if subtotal < 0:
            raise ValueError("Subtotal must be positive")
        return round(subtotal * (1.0 + self.tax_rate), 2)
