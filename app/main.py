from typing import List

from fastapi import FastAPI, HTTPException, status
from pymongo.errors import DuplicateKeyError
from fastapi import UploadFile, File
import csv
from io import StringIO
from app.models import CaseCreate, CaseNoteCreate, CaseStatusUpdate, RiskRules, Transaction
from app.risk_engine import calculate_risk, get_risk_rules
from app.database import cases, imports, risk_settings, transactions
from typing import Optional
from fastapi import Query
from fastapi import HTTPException

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
from bson import ObjectId
from bson.errors import InvalidId
app = FastAPI(title="BankGuard AML")

HIGH_RISK_THRESHOLD = 50


def initial_status(risk_score: int) -> str:
    """Assign an investigation status to a newly created transaction."""
    if risk_score >= HIGH_RISK_THRESHOLD:
        return "Under Review"
    return "Pending"


def serialize_case(case):
    case["_id"] = str(case["_id"])
    return case

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://bank-guard-aml-frontend.vercel.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Create one transaction
@app.post("/transactions", status_code=status.HTTP_201_CREATED)
def create_transaction(transaction: Transaction):

    score, reasons = calculate_risk(transaction, get_risk_rules())

    data = transaction.model_dump()
    data["risk_score"] = score
    data["reasons"] = reasons
    data["status"] = initial_status(score)

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
    risk_rules = get_risk_rules()

    for transaction in transactions_list:

        score, reasons = calculate_risk(transaction, risk_rules)

        data = transaction.model_dump()
        data["risk_score"] = score
        data["reasons"] = reasons
        data["status"] = initial_status(score)

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

    score, reasons = calculate_risk(transaction, get_risk_rules())

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
@app.post("/transactions/import")
async def import_transactions(file: UploadFile = File(...)):

    content = await file.read()
    csv_text = content.decode("utf-8")

    reader = csv.DictReader(StringIO(csv_text))

    imported = 0
    duplicates = 0
    risk_rules = get_risk_rules()

    for row in reader:
        transaction = Transaction(
            transaction_id=row["transaction_id"],
            customer_id=row["customer_id"],
            amount=float(row["amount"]),
            country=row["country"],
            merchant=row["merchant"],
            timestamp=row["timestamp"],
        )

        score, reasons = calculate_risk(transaction, risk_rules)

        data = transaction.model_dump()
        data["risk_score"] = score
        data["reasons"] = reasons
        data["status"] = initial_status(score)
        data["created_at"] = transaction.timestamp

        try:
            transactions.insert_one(data)
            imported += 1
        except DuplicateKeyError:
            duplicates += 1

    # Save import history (outside the loop)
    imports.insert_one({
        "file_name": file.filename,
        "imported": imported,
        "duplicates": duplicates,
        "total_rows": imported + duplicates,
        "status": "Completed",
        "created_at": datetime.utcnow(),
    })

    return {
        "imported": imported,
        "duplicates": duplicates,
    }
@app.get("/imports")
def get_import_history():

    history = []

    for item in imports.find().sort("created_at", -1):
        item["_id"] = str(item["_id"])
        history.append(item)

    return {"imports": history}


@app.get("/settings/risk-rules")
def get_settings_risk_rules():
    return get_risk_rules().model_dump()


@app.put("/settings/risk-rules")
def update_settings_risk_rules(rules: RiskRules):
    data = rules.model_dump()
    risk_settings.replace_one(
        {"_id": "risk_rules"},
        {"_id": "risk_rules", **data},
        upsert=True,
    )
    return data


@app.get("/cases")
def get_cases():
    return {"cases": [serialize_case(case) for case in cases.find().sort("created_at", -1)]}


@app.post("/cases")
def create_case(case_request: CaseCreate):
    transaction = transactions.find_one(
        {"transaction_id": case_request.transaction_id}
    )
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found.")

    existing_case = cases.find_one(
        {
            "transaction_id": case_request.transaction_id,
            "status": {"$ne": "Resolved"},
        }
    )
    if existing_case:
        existing_case = serialize_case(existing_case)
        existing_case["already_exists"] = True
        return existing_case

    now = datetime.utcnow()
    new_case = {
        "transaction_id": transaction["transaction_id"],
        "customer_id": transaction["customer_id"],
        "amount": transaction["amount"],
        "country": transaction["country"],
        "merchant": transaction["merchant"],
        "risk_score": transaction.get("risk_score", 0),
        "reasons": transaction.get("reasons", []),
        "transaction_timestamp": transaction["timestamp"],
        "status": "Open",
        "notes": [],
        "resolution": "",
        "created_at": now,
        "updated_at": now,
    }
    result = cases.insert_one(new_case)
    new_case["_id"] = str(result.inserted_id)
    return new_case


@app.post("/cases/{case_id}/notes")
def add_case_note(case_id: str, note_request: CaseNoteCreate):
    try:
        object_id = ObjectId(case_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid case ID.")

    note_text = note_request.note.strip()
    if not note_text:
        raise HTTPException(status_code=422, detail="A note cannot be empty.")

    result = cases.update_one(
        {"_id": object_id},
        {
            "$push": {"notes": {"text": note_text, "created_at": datetime.utcnow()}},
            "$set": {"updated_at": datetime.utcnow()},
        },
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Case not found.")

    return serialize_case(cases.find_one({"_id": object_id}))


@app.patch("/cases/{case_id}")
def update_case(case_id: str, update: CaseStatusUpdate):
    try:
        object_id = ObjectId(case_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid case ID.")

    if update.status == "Resolved" and not update.resolution.strip():
        raise HTTPException(
            status_code=422,
            detail="Add a resolution summary before resolving the case.",
        )

    result = cases.update_one(
        {"_id": object_id},
        {
            "$set": {
                "status": update.status,
                "resolution": (
                    update.resolution.strip() if update.status == "Resolved" else ""
                ),
                "updated_at": datetime.utcnow(),
            }
        },
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Case not found.")

    return serialize_case(cases.find_one({"_id": object_id}))


@app.delete("/imports/{import_id}")
def delete_import_history(import_id: str):
    try:
        object_id = ObjectId(import_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid import history ID.")

    result = imports.delete_one({"_id": object_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Import history record not found.")

    return {"message": "Import history record deleted successfully."}
