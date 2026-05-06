# main.py — FastAPI application entry point — COMPLETE VERSION v2.1
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from pathlib import Path
from app.database import test_connection, engine, Base

# Import ALL routers
from app.routers import (
    vendors, rfq, quotations, purchase_orders,
    invoices, dashboard, sap, contracts,
    negotiations, checklists, audit, workflow
)
from app.routers import commercial_governance

# ── Lifespan (replaces deprecated @app.on_event) ─────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    Base.metadata.create_all(bind=engine)
    test_connection()
    print("S2P System v2.1 started - Full pipeline automation active")
    yield
    # Shutdown (optional cleanup)
    print("S2P System shutting down...")

# ── App Instance ──────────────────────────────────────────────
app = FastAPI(
    title       = "S2P Automation System — Matrix Comsec",
    description = "AI-powered Source-to-Pay platform | All BRD requirements implemented",
    version     = "2.1.0",
    docs_url    = "/docs",
    redoc_url   = "/redoc",
    lifespan    = lifespan
)

# ── CORS ──────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["*"],
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

# ── Register ALL routers ──────────────────────────────────────
app.include_router(vendors.router,          prefix="/api/vendors",         tags=["Vendors"])
app.include_router(rfq.router,              prefix="/api/rfq",             tags=["RFQ"])
app.include_router(quotations.router,       prefix="/api/quotations",      tags=["Quotations"])
app.include_router(purchase_orders.router,  prefix="/api/purchase-orders", tags=["Purchase Orders"])
app.include_router(invoices.router,         prefix="/api/invoices",        tags=["Invoices"])
app.include_router(dashboard.router,        prefix="/api/dashboard",       tags=["Dashboard"])
app.include_router(sap.router,              prefix="/api/sap",             tags=["SAP Integration"])
app.include_router(contracts.router,        prefix="/api/contracts",       tags=["Contracts"])
app.include_router(negotiations.router,     prefix="/api/negotiations",    tags=["Negotiations"])
app.include_router(checklists.router,       prefix="/api/checklists",      tags=["Checklists"])
app.include_router(audit.router,            prefix="/api/audit",           tags=["Audit Trail"])
app.include_router(workflow.router,             prefix="/api/workflow",        tags=["S2P Workflow Pipeline"])
app.include_router(commercial_governance.router, prefix="/api/governance",      tags=["Commercial Governance"])

# ── Serve Frontend Static Files ───────────────────────────────
FRONTEND_DIR = Path(__file__).parent.parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

# ── Root: serve index.html ─────────────────────────────────────
@app.get("/")
def root():
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"system": "S2P Automation — Matrix Comsec Pvt. Ltd.", "status": "running", "docs": "/docs"}

@app.get("/health")
def health_check():
    return {"status": "healthy", "version": "2.1.0"}

# ── Serve individual frontend pages ────────────────────────────
@app.get("/pages/{page_name}")
def serve_page(page_name: str):
    page_path = FRONTEND_DIR / "pages" / page_name
    if page_path.exists():
        return FileResponse(str(page_path))
    return {"error": f"Page {page_name} not found"}, 404