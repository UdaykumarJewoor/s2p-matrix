# database.py — MySQL connection setup using SQLAlchemy
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import os

load_dotenv()

# Build connection URL from .env
DB_USER     = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_HOST     = os.getenv("DB_HOST", "localhost")
DB_PORT     = os.getenv("DB_PORT", "3306")
DB_NAME     = os.getenv("DB_NAME", "s2p_matrix")

DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Create engine
engine = create_engine(
    DATABASE_URL,
    echo=False,           # Set True to see SQL logs
    pool_pre_ping=True,   # Auto-reconnect if connection drops
    pool_size=10,
    max_overflow=20
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for all models
Base = declarative_base()

# Dependency — used in every API route
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Test connection
def test_connection():
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        print("Database connected successfully!")
        db.close()
    except Exception as e:
        print(f"Database connection failed: {e}")
        return False

# --- FORCE LOAD ALL MODELS TO PREVENT MAPPING 500 ERRORS ---
from app.models.vendor import Vendor, VendorDocument
from app.models.rfq import RFQ, RFQItem, RFQVendor
from app.models.quotation import Quotation, QuotationItem
from app.models.purchase_order import PurchaseOrder, POItem
from app.models.invoice import Invoice, GRN, GRNItem
from app.models.payment import Payment, VendorPerformance
