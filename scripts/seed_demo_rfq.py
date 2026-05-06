"""
scripts/seed_demo_rfq.py
────────────────────────────────────────────────────────────────
Seeds realistic demo RFQs for Matrix Comsec S2P pipeline testing.
Creates 5 RFQs covering real security procurement scenarios.

Run AFTER seed_vendors.py:
  $env:PYTHONUTF8 = "1"
  .\\venv\\Scripts\\python.exe scripts\\seed_demo_rfq.py
"""

import sys, os, random
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

# Import ALL models first so SQLAlchemy mapper initialises correctly
from app.database import SessionLocal
from app.models.vendor import Vendor, VendorDocument
from app.models.payment import Payment, VendorPerformance
from app.models.rfq import RFQ, RFQItem, RFQVendor, CommodityCategory
from app.models.quotation import Quotation, QuotationItem
from app.models.purchase_order import PurchaseOrder, POItem
from app.models.invoice import Invoice, GRN, GRNItem
from app.utils.audit import AuditLog
from datetime import date, datetime, timedelta
from sqlalchemy import func

db = SessionLocal()

# ── Ensure commodity categories exist ───────────────────────
CATEGORIES = [
    ("CCTV & Video Surveillance", "Electronic"),
    ("Access Control Systems",    "Electronic"),
    ("Fire Detection Systems",    "Electronic"),
    ("Network Infrastructure",    "Electronic"),
    ("Mechanical Hardware",       "Mechanical"),
]

cat_ids = {}
for name, parent in CATEGORIES:
    existing = db.query(CommodityCategory).filter(
        CommodityCategory.name == name
    ).first()
    if not existing:
        cat = CommodityCategory(
            name            = name,
            parent_category = parent,
            description     = f"{name} for Matrix Comsec procurement",
            is_active       = True
        )
        db.add(cat)
        db.flush()
        cat_ids[name] = cat.id
        print(f"  Created category: {name}")
    else:
        cat_ids[name] = existing.id
        print(f"  Category exists: {name} (id={existing.id})")

db.commit()

# ── Helper ───────────────────────────────────────────────────
def rfq_num(db):
    year  = datetime.now().year
    count = db.query(func.count(RFQ.id)).scalar()
    return f"RFQ-{year}-{str(count + 1).zfill(4)}"

today    = date.today()
deadline = today + timedelta(days=14)

# ── Demo RFQs ────────────────────────────────────────────────
DEMO_RFQS = [
    {
        "title"          : "CCTV Surveillance System — Warehouse Block A",
        "description"    : "Supply and installation of IP cameras, NVRs, and storage for 15,000 sq ft warehouse. Bosch/Hikvision preferred. 3-year warranty mandatory.",
        "category"       : "CCTV & Video Surveillance",
        "estimated_value": 850000.00,
        "items"          : [
            ("IP Camera 4MP",           20,  "PCS", "Min 4MP, IR 30m, PoE, H.265+, IP67"),
            ("IP Camera 8MP 4K",        4,   "PCS", "4K resolution, motorized varifocal, analytics"),
            ("NVR 16 Channel",          2,   "PCS", "16-ch PoE NVR, 8TB, ONVIF compliant"),
            ("Hard Disk 4TB Surveillance", 4, "PCS", "WD Purple or Seagate SkyHawk"),
            ("PoE Switch 16 Port",      2,   "PCS", "16-port 250W PoE+, managed"),
            ("Cat6 Cable (305m Box)",   3,   "BOX", "Shielded CAT6, 305m per box"),
        ]
    },
    {
        "title"          : "Access Control — Head Office Entry Points",
        "description"    : "Biometric access control for 8 entry points including main gate. Face recognition with attendance integration. Must support 5,000 users.",
        "category"       : "Access Control Systems",
        "estimated_value": 620000.00,
        "items"          : [
            ("Face Recognition Terminal",  8,  "PCS", "Face + card + PIN, POE, 5000 users, OSDP"),
            ("Access Control Panel",       2,  "PCS", "4-door controller, TCP/IP, 50,000 events"),
            ("Electric Door Lock",         8,  "PCS", "Fail-safe, 600kg holding, 12VDC"),
            ("Magnetic Lock 600lb",        4,  "PCS", "Surface mount, LED indicator, monitoring"),
            ("Exit Button",               12,  "PCS", "Stainless steel, IP55"),
            ("Proximity Card",           200,  "PCS", "13.56 MHz MIFARE, printable"),
        ]
    },
    {
        "title"          : "Fire Detection System — Manufacturing Plant",
        "description"    : "Addressable fire alarm system for 3-floor manufacturing plant. Bosch authorised system. Includes smoke, heat, and manual call points with central panel.",
        "category"       : "Fire Detection Systems",
        "estimated_value": 480000.00,
        "items"          : [
            ("Fire Alarm Panel 32 Zone",     1,  "PCS", "Addressable, UL/ULC listed, Bosch/Hochiki"),
            ("Addressable Smoke Detector",  45,  "PCS", "Optical, addressable loop, self-testing"),
            ("Heat Detector",              20,  "PCS", "Fixed temp 57C + ROR, addressable"),
            ("Manual Call Point",          12,  "PCS", "Break glass, weatherproof, red"),
            ("Sounder Strobe",             15,  "PCS", "Red, 97dB, multi-tone, EN54 certified"),
            ("CO Detector",                6,   "PCS", "Addressable CO detector, 10-year sensor"),
        ]
    },
    {
        "title"          : "Network Infrastructure — CCTV Backbone Upgrade",
        "description"    : "Structured cabling and network backbone for 200-camera CCTV expansion. Includes fibre, switches, and rack infrastructure across 3 buildings.",
        "category"       : "Network Infrastructure",
        "estimated_value": 320000.00,
        "items"          : [
            ("Managed Switch 24 Port",      4,   "PCS", "L2/L3, 24x1G + 4xSFP+, PoE+, ONVIF-aware"),
            ("Fiber Optic Cable (500m)",    2,   "DRUM", "OM4 multimode, armoured, outdoor rated"),
            ("Patch Panel 24 Port",         4,   "PCS", "Cat6A, toolless, 1U rackmount"),
            ("Network Cabinet 12U",         2,   "PCS", "Wall mount, lockable, ventilated"),
            ("UPS 2KVA",                   2,   "PCS", "Online double-conversion, LCD display"),
            ("Cat6 Cable (305m Box)",       4,   "BOX", "Shielded CAT6, grey, 305m per box"),
        ]
    },
    {
        "title"          : "Mechanical Hardware — Cable Management & Conduits",
        "description"    : "Supply of GI pipes, cable trays, conduits, and accessories for annual maintenance and new installations across all Matrix Comsec sites.",
        "category"       : "Mechanical Hardware",
        "estimated_value": 145000.00,
        "items"          : [
            ("GI Pipe 1 inch (6m)",        50,  "PCS", "GI medium class, IS:1239"),
            ("Cable Tray 2 inch",          200,  "MTR", "Galvanised, perforated, 2-inch width"),
            ("Conduit 20mm (30m)",          30,  "COIL", "PVC rigid, ISI marked, 20mm dia"),
            ("Junction Box IP66",           40,  "PCS", "Polycarbonate, 100x100x70mm, IP66"),
            ("Wall Bracket Heavy Duty",     60,  "PCS", "GI, adjustable, for 1-inch pipe"),
            ("Cable Gland M20",            200,  "PCS", "Nylon, IP68, for 6–12mm cable"),
        ]
    },
]

print(f"\nSeeding {len(DEMO_RFQS)} demo RFQs...")

for rfq_data in DEMO_RFQS:
    # Check if already exists
    existing = db.query(RFQ).filter(RFQ.title == rfq_data["title"]).first()
    if existing:
        print(f"  SKIP (exists): {rfq_data['title'][:50]}")
        continue

    rfq = RFQ(
        rfq_number      = rfq_num(db),
        title           = rfq_data["title"],
        description     = rfq_data["description"],
        category_id     = cat_ids.get(rfq_data["category"]),
        issue_date      = today,
        deadline        = deadline,
        estimated_value = rfq_data["estimated_value"],
        status          = "Draft",
        created_by      = "Bhavesh"
    )
    db.add(rfq)
    db.flush()

    for desc, qty, unit, spec in rfq_data["items"]:
        db.add(RFQItem(
            rfq_id        = rfq.id,
            description   = desc,
            quantity      = qty,
            unit          = unit,
            specification = spec
        ))

    db.commit()
    print(f"  Created: {rfq.rfq_number} — {rfq_data['title'][:50]}")
    print(f"           {len(rfq_data['items'])} items | Est. INR {rfq_data['estimated_value']:,.0f}")

db.close()
print(f"\nDone! Open http://localhost:8000/docs and test the pipeline.")
print(f"Run: POST /api/workflow/run with rfq_id=1 to 5")
