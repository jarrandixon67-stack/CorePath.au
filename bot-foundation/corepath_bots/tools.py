"""Deterministic planning tools. No clinical scoring or financial transactions."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def number(value) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("Boolean is not a numeric input")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("Use a finite numeric input") from exc
    if not result.is_finite() or abs(result) > Decimal("1000000000000"):
        raise ValueError("Use a finite input within the supported range")
    return result


def money(value) -> str:
    return str(number(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def budget(income: list[dict], expenses: list[dict]) -> dict:
    """Annualised averages, not a bill-due cash-flow calendar. All amounts >= 0."""
    periods = {"weekly": Decimal(52), "fortnightly": Decimal(26),
               "monthly": Decimal(12), "quarterly": Decimal(4), "annual": Decimal(1)}

    def total(items):
        annual = Decimal(0)
        for item in items:
            amount = number(item["amount"])
            if amount < 0 or item["frequency"] not in periods:
                raise ValueError("Use nonnegative amounts and a supported frequency")
            annual += amount * periods[item["frequency"]]
        return annual

    earnings, spending = total(income), total(expenses)
    return {"annual_income": money(earnings), "annual_expenses": money(spending),
            "monthly_average_surplus": money((earnings - spending) / 12),
            "fortnightly_average_surplus": money((earnings - spending) / 26),
            "assumptions": "52 weeks / 26 fortnights per annual average; bill dates, leap years, tax, interest and variable amounts are not inferred."}


def bmi(weight_kg, height_cm, *, adult: bool) -> dict:
    if not adult:
        raise ValueError("This simple adult BMI calculation is not a child assessment")
    weight, height = number(weight_kg), number(height_cm)
    if not Decimal("20") <= weight <= Decimal("500") or not Decimal("100") <= height <= Decimal("250"):
        raise ValueError("Check the units: adult weight in kg and height in cm")
    value = weight / (height / 100) ** 2
    return {"bmi": str(value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)),
            "limitations": "BMI is a limited screening measure, not a diagnosis, body composition measure or clearance to exercise."}


def compare_decisions(weights: dict, options: dict) -> dict:
    if not weights or not options or len(options) < 2:
        raise ValueError("Supply weighted criteria and at least two options")
    numeric = {key: number(value) for key, value in weights.items()}
    if any(value < 0 for value in numeric.values()) or sum(numeric.values()) <= 0:
        raise ValueError("Weights must be nonnegative with a positive total")
    total = sum(numeric.values())
    scores = {}
    for name, ratings in options.items():
        if set(ratings) != set(weights):
            raise ValueError("Every option needs the same criteria")
        values = {key: number(value) for key, value in ratings.items()}
        if any(not 0 <= value <= 10 for value in values.values()):
            raise ValueError("Rate each criterion from 0 to 10; higher must mean more desirable")
        scores[name] = str((sum(numeric[k] * values[k] for k in weights) / total).quantize(Decimal("0.01")))
    return {"scores": scores, "limits": "A reflection aid, not a decision. Examine uncertainty, safety, nonnegotiable values and reversibility separately; scores do not override them."}


def smart_goal(*, specific: str, measure: str, feasible_step: str, relevance: str,
               deadline: str, review_date: str, accountability: str) -> dict:
    values = locals().copy()
    if any(not isinstance(value, str) or not value.strip() for value in values.values()):
        raise ValueError("Every SMART goal and accountability field needs a value")
    return {key: value.strip() for key, value in values.items()}
