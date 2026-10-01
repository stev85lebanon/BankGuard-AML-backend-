from app.database import risk_settings
from app.models import RiskRules


def get_risk_rules() -> RiskRules:
    stored_rules = risk_settings.find_one({"_id": "risk_rules"})
    if stored_rules is None:
        return RiskRules()

    stored_rules.pop("_id", None)
    return RiskRules.model_validate(stored_rules)


def calculate_risk(transaction, rules: RiskRules | None = None):
    active_rules = rules or get_risk_rules()
    score = 0
    reasons = []

    if transaction.amount > active_rules.large_transaction_threshold:
        score += active_rules.large_transaction_points
        reasons.append("Large transaction")

    high_risk_countries = {country.casefold() for country in active_rules.high_risk_countries}
    if transaction.country.strip().casefold() in high_risk_countries:
        score += active_rules.high_risk_country_points
        reasons.append("High-risk country")

    if transaction.amount > active_rules.above_normal_threshold:
        score += active_rules.above_normal_points
        reasons.append("Above normal threshold")

    return score, reasons
