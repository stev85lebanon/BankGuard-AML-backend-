from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()

client = MongoClient(os.getenv("MONGO_URI"))
db = client[os.getenv("DATABASE_NAME")]

transactions = db.transactions

# Create only once; MongoDB ignores it if it already exists.
transactions.create_index("transaction_id", unique=True)