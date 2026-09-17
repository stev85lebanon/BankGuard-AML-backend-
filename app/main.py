from typing import List

from fastapi import FastAPI, HTTPException, status
from pymongo.errors import DuplicateKeyError

from app.models import Transaction
from app.risk_engine import calculate_risk
from app.database import transactions
from typing import Optional
from fastapi import Query
from fastapi import HTTPException

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="BankGuard AML")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Create one transaction
@app.post("/transactions", status_code=status.HTTP_201_CREATED)
def create_transaction(transaction: Transaction):

    score, reasons = calculate_risk(transaction)

    data = transaction.model_dump()
    data["risk_score"] = score
    data["reasons"] = reasons

    try:
        result = transactions.insert_one(data)
        data["_id"] = str(result.inserted_id)
        return data

    except DuplicateKeyError:
        raise HTTPException(
            status_code=409,
            detail="Transaction ID already exists."
        )


# Create multiple transactions
@app.post("/transactions/bulk", status_code=status.HTTP_201_CREATED)
def create_transactions_bulk(transactions_list: List[Transaction]):

    inserted = []

    for transaction in transactions_list:

        score, reasons = calculate_risk(transaction)

        data = transaction.model_dump()
        data["risk_score"] = score
        data["reasons"] = reasons

        try:
            result = transactions.insert_one(data)
            data["_id"] = str(result.inserted_id)
            inserted.append(data)

        except DuplicateKeyError:
            continue

    return {
        "inserted_count": len(inserted),
        "transactions": inserted
    }




@app.get("/transactions")
def get_transactions(
    country: Optional[str] = Query(None),
    min_risk: Optional[int] = Query(None)
):
    query = {}

    if country:
        query["country"] = country

    if min_risk is not None:
        query["risk_score"] = {"$gte": min_risk}

    results = []

    for transaction in transactions.find(query):
        transaction["_id"] = str(transaction["_id"])
        results.append(transaction)

    return {
        "count": len(results),
        "transactions": results
    }


@app.get("/transactions/{transaction_id}")
def get_transaction(transaction_id: str):

    transaction = transactions.find_one({"transaction_id": transaction_id})

    if not transaction:
        raise HTTPException(
            status_code=404,
            detail="Transaction not found."
        )

    transaction["_id"] = str(transaction["_id"])

    return transaction

@app.put("/transactions/{transaction_id}")
def update_transaction(transaction_id: str, transaction: Transaction):

    existing = transactions.find_one({"transaction_id": transaction_id})

    if not existing:
        raise HTTPException(
            status_code=404,
            detail="Transaction not found."
        )

    score, reasons = calculate_risk(transaction)

    updated = transaction.model_dump()
    updated["risk_score"] = score
    updated["reasons"] = reasons

    # Preserve existing investigation fields
    updated["status"] = existing.get("status", "Pending")
    updated["created_at"] = existing.get("created_at", transaction.timestamp)

    transactions.update_one(
        {"transaction_id": transaction_id},
        {"$set": updated}
    )

    result = transactions.find_one({"transaction_id": transaction_id})
    result["_id"] = str(result["_id"])

    return result

from app.models import StatusUpdate

@app.patch("/transactions/{transaction_id}/status")
def update_status(transaction_id: str, status_update: StatusUpdate):

    result = transactions.update_one(
        {"transaction_id": transaction_id},
        {"$set": {"status": status_update.status}}
    )

    if result.matched_count == 0:
        raise HTTPException(
            status_code=404,
            detail="Transaction not found."
        )

    transaction = transactions.find_one({"transaction_id": transaction_id})
    transaction["_id"] = str(transaction["_id"])

    return transaction

@app.delete("/transactions/{transaction_id}")
def delete_transaction(transaction_id: str):

    result = transactions.delete_one({"transaction_id": transaction_id})

    if result.deleted_count == 0:
        raise HTTPException(
            status_code=404,
            detail="Transaction not found."
        )

    return {
        "message": f"Transaction {transaction_id} deleted successfully."
    }
