from pydantic import BaseModel, Field, model_validator
from pydantic import field_validator
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


class RiskRules(BaseModel):
    large_transaction_threshold: float = Field(default=100000, gt=0)
    large_transaction_points: int = Field(default=50, ge=0, le=100)
    high_risk_country_points: int = Field(default=30, ge=0, le=100)
    above_normal_threshold: float = Field(default=50000, gt=0)
    above_normal_points: int = Field(default=20, ge=0, le=100)
    high_risk_countries: list[str] = Field(
        default_factory=lambda: ["North Korea", "Iran", "Syria"]
    )

    @field_validator("high_risk_countries")
    @classmethod
    def normalize_countries(cls, countries: list[str]) -> list[str]:
        normalized = []
        seen = set()
        for country in countries:
            name = country.strip()
            if not name:
                raise ValueError("Country names cannot be empty.")
            key = name.casefold()
            if key not in seen:
                normalized.append(name)
                seen.add(key)
        return normalized

    @model_validator(mode="after")
    def validate_amount_thresholds(self):
        if self.above_normal_threshold >= self.large_transaction_threshold:
            raise ValueError(
                "The above-normal amount threshold must be lower than the large transaction threshold."
            )
        return self


class CaseCreate(BaseModel):
    transaction_id: str


class CaseNoteCreate(BaseModel):
    note: str = Field(min_length=1, max_length=2000)


class CaseStatusUpdate(BaseModel):
    status: Literal["Open", "Investigating", "Resolved"]
    resolution: str = Field(default="", max_length=4000)
