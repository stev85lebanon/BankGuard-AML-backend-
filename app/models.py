from pydantic import BaseModel
from datetime import datetime
from typing import Literal

class Transaction(BaseModel):
    transaction_id: str
    customer_id: str
    amount: float
    country: str
    merchant: str
    timestamp: datetime


class StatusUpdate(BaseModel):
    status: Literal["Pending", "Under Review", "Cleared", "Escalated"]