HIGH_RISK_COUNTRIES = [
    "North Korea",
    "Iran",
    "Syria"
]

def calculate_risk(transaction):

    score = 0
    reasons = []

    if transaction.amount > 100000:
        score += 50
        reasons.append("Large transaction")

    if transaction.country in HIGH_RISK_COUNTRIES:
        score += 30
        reasons.append("High-risk country")

    if transaction.amount > 50000:
        score += 20
        reasons.append("Above normal threshold")

    return score, reasons