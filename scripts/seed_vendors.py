"""
scripts/seed_vendors.py
────────────────────────────────────────────────────────────────
Seed 1,000+ realistic vendors for Matrix Comsec S2P simulation.

Industry context (from BRD):
  • Matrix Comsec is a Bosch-partner security systems manufacturer, Gujarat
  • 85 % Electronic procurement (CCTV, access control, fire, networking)
  • 15 % Mechanical (cable trays, GI pipes, conduits, enclosures)

Run:
  cd c:\\Users\\calve\\OneDrive\\Desktop\\s2p_matrix
  python scripts/seed_vendors.py
"""

import sys
import os
import random
from datetime import datetime, date, timedelta

# ── path setup so we can import app modules ──────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..","backend"))

# Import ALL models first so SQLAlchemy mapper initialises correctly
from sqlalchemy.orm import Session
from app.database import SessionLocal, engine, Base

# Models — must all be imported before any query runs
from app.models.vendor import Vendor, VendorDocument
from app.models.payment import Payment, VendorPerformance
from app.models.rfq import RFQ, RFQItem, RFQVendor, CommodityCategory
from app.models.quotation import Quotation, QuotationItem
from app.models.purchase_order import PurchaseOrder, POItem
from app.models.invoice import Invoice, GRN, GRNItem
from app.utils.audit import AuditLog

# ── Seed data pools ──────────────────────────────────────────

OEM_BRANDS = [
    "Bosch", "Hikvision", "Dahua", "Honeywell", "Axis", "Hanwha",
    "Pelco", "Genetec", "Milestone", "Avigilon", "Samsung Techwin",
    "Uniview", "CP Plus", "Godrej", "Matrix Comsec", "HID Global",
    "Suprema", "ZKTeco", "Rosslare", "FAAC", "Dormakaba",
    "Siemens", "Tyco", "Hochiki", "Napco", "Paradox", "DSC",
    "Cisco", "D-Link", "TP-Link", "Netgear", "Ubiquiti", "Ruckus",
    "APC", "Eaton", "Socomec", "Legrand", "Schneider Electric",
    "Armoured Polymers", "Mersen", "3M India"
]

ELECTRONIC_COMPANIES = [
    # Ahmedabad-based
    "Secure Vision Systems", "AlphaTech Security", "Prime Surveillance India",
    "SafeNet Distributors", "Gujarat Security Hub", "CamTech India",
    "NetSecure Pvt Ltd", "DigiWatch Enterprises", "Vigil Security Systems",
    "TechGuard Solutions", "SecureLink India", "FireSafe Systems",
    "ElectroPro Security", "ClearView Technologies", "TechVision India",
    "AccessPro Systems", "SmartSafe Solutions", "Sentinel Technologies",
    "GuardPlus Pvt Ltd", "WatchTower Systems",
    # Surat
    "Diamond City Electronics", "SuratTech Security", "Textile Town Security",
    "SilkRoute Distributors", "Udhna Electronics Hub",
    # Vadodara
    "Baroda Security Systems", "PetroCity Electronics", "RefineryEdge Tech",
    "Vadodara Tech Hub", "Laxmi Security Solutions",
    # Rajkot
    "Rajkot Automation", "SaurashtraElec Pvt Ltd", "JamnaTech Security",
    # Mumbai
    "BombaySec Distributors", "MumbaiTech Electronics", "MaxSecurity India",
    "Maharashtra Security Hub", "Andheri Electronics", "Mulund Tech Solutions",
    "Navi Mumbai Surveillance", "Thane Security Systems",
    # Delhi / NCR
    "Capital Security Systems", "DelhiTech Distributors", "GurgaonElec Pvt Ltd",
    "Noida Security Hub", "Faridabad Electronics",
    # Bangalore
    "BangaloreTech Security", "Silicon Valley Electronics", "Tech Park Security",
    "KarnatakaSec Systems", "Whitefield Electronics",
    # Chennai
    "Chennai Security Systems", "TamilNadu Surveillance", "Anna Nagar Electronics",
    "Perambur Tech Hub", "Ambattur Electronics",
    # Hyderabad
    "Hyderabad Security Hub", "CyberCity Electronics", "HiTechCity Systems",
    "SecunderabadElec", "HITEX Security Solutions",
    # Pune
    "Pune Security Systems", "PCMC Electronics", "Hinjewadi Tech Hub",
    "PuneDistributors Pvt Ltd",
    # Other Gujarat
    "Anand Security Hub", "BharuchTech Systems", "MehsanaSec Pvt Ltd",
    "GandhinagarElec", "JunagadhSecurity", "BhavnagarTech",
    # Pan-India distributors
    "National Security Distributors", "Pan India Electronics",
    "AllIndia Security Hub", "CountryWide Surveillance", "MegaTech India",
    "StarSec Systems", "Eagle Eye Electronics", "FalconTech India",
    "HawkEye Security", "Infinity Security Solutions",
    "Optima Security Pvt Ltd", "Vertex Electronics", "Apex Security India",
    "Zenith Surveillance", "Pinnacle Security Systems",
    "Crown Security Hub", "Royal Electronics India", "Elite Tech Security",
    "Premier Security India", "Sovereign Security Systems",
    # Specialised
    "FireAlert India", "FlameStop Electronics", "SmokeDetect Systems",
    "AlarmTech India", "SirenPro Systems", "PanicPro Electronics",
    "IntruderStop India", "PerimeterGuard Tech", "ZoneAlert Systems",
    "BiometricPro India", "FaceID Tech India", "IRISSec Systems",
    "VeinMatch Electronics", "FingerPrint India", "PalmVein Tech",
    "PTZmaster India", "ThermalSec Systems", "LPRSolutions India",
    "VideoAnalytics Pro", "AICamera India", "EdgeAI Security",
    "CloudSec India", "DeepLearning Surveillance", "SmartCity Security",
    "IoTSec India", "Connected Security", "CyberPhysical Systems",
    "SecureCloud India", "RemoteGuard Tech", "CentralStation India",
]

MECHANICAL_COMPANIES = [
    "GI Pipe Traders", "Cable Tray Manufacturers India", "Conduit World",
    "Enclosure Systems India", "Metal Works Gujarat", "Baroda Metal Traders",
    "Ahmedabad Hardware Hub", "Gujarat Fabricators", "PipeLine Solutions",
    "CableTray Pro India", "Jyoti Fabrication Works", "Shri Ram Metal Works",
    "Bhagwati Steel Industries", "Tulsi Metal Traders", "Shanker Hardware",
    "Vijay Electrical Accessories", "Mahavir Cable Accessories", "Jai Balaji Steel",
    "Durga Metal Products", "Ambika Hardware Stores", "Saraswati Steel",
    "Ganesh Metal Works", "Laxmi Hardware Traders", "Radha Krishna Metal",
    "Ram Ji Fabricators", "Sai Baba Steel Industries", "Hanuman Metal Works",
    "Shiva Steel & Hardware", "Parvati Metal Industries", "Gauri Shankar Steel",
    "Industrial Hardware Hub", "PipeFit India", "Conduit King India",
    "EnclosureMax India", "Cabinet World", "BracketPro Systems",
    "MountingMaster India", "TrayFit Gujarat", "WirewayPro",
    "CableManagement India", "DuctPro Systems", "RaceWay India",
]

BOTH_COMPANIES = [
    "Matrix Distributors India", "Omni Security Solutions",
    "Complete Security Systems", "Integrated Security India",
    "TotalSec Systems Pvt Ltd", "MultiTech Security",
    "Convergence Security", "Unified Security Hub",
    "CombiSec Electronics", "AllRound Security India",
    "Comprehensive Security", "Universal Security Systems",
    "Complete Tech India", "EndToEnd Security", "FullSpec Systems",
    "Broad Base Electronics", "WideRange Security", "OmniSpec India",
    "AllSpec Security Hub", "Diversified Tech India",
]

SERVICE_COMPANIES = [
    "SecureAMC Services India", "MaintenancePro Security",
    "AMCPro India", "ServiceFirst Security", "TechSupport Security",
    "OnSite Security Services", "FieldForce India", "TechCare AMC",
    "24x7 Security Services", "RapidResponse Maintenance",
    "ProAMC India", "EliteMaintenance Security", "SilverShield Services",
    "GoldCare Security", "PlatinumAMC India",
]

INDIAN_CITIES = [
    # Gujarat (preferred — Matrix Comsec is Gujarat-based)
    ("Ahmedabad", "Gujarat", "380001"),
    ("Surat", "Gujarat", "395001"),
    ("Vadodara", "Gujarat", "390001"),
    ("Rajkot", "Gujarat", "360001"),
    ("Gandhinagar", "Gujarat", "382010"),
    ("Anand", "Gujarat", "388001"),
    ("Bharuch", "Gujarat", "392001"),
    ("Mehsana", "Gujarat", "384001"),
    ("Junagadh", "Gujarat", "362001"),
    ("Bhavnagar", "Gujarat", "364001"),
    # Metro
    ("Mumbai", "Maharashtra", "400001"),
    ("Pune", "Maharashtra", "411001"),
    ("Nagpur", "Maharashtra", "440001"),
    ("Delhi", "Delhi", "110001"),
    ("Gurugram", "Haryana", "122001"),
    ("Noida", "Uttar Pradesh", "201301"),
    ("Bangalore", "Karnataka", "560001"),
    ("Chennai", "Tamil Nadu", "600001"),
    ("Hyderabad", "Telangana", "500001"),
    ("Kolkata", "West Bengal", "700001"),
    ("Chandigarh", "Punjab", "160001"),
    ("Jaipur", "Rajasthan", "302001"),
    ("Lucknow", "Uttar Pradesh", "226001"),
    ("Indore", "Madhya Pradesh", "452001"),
    ("Bhopal", "Madhya Pradesh", "462001"),
    ("Kochi", "Kerala", "682001"),
    ("Bhubaneswar", "Odisha", "751001"),
    ("Coimbatore", "Tamil Nadu", "641001"),
    ("Visakhapatnam", "Andhra Pradesh", "530001"),
    ("Patna", "Bihar", "800001"),
]

GST_STATES = {
    "Gujarat": "24", "Maharashtra": "27", "Delhi": "07", "Haryana": "06",
    "Uttar Pradesh": "09", "Karnataka": "29", "Tamil Nadu": "33",
    "Telangana": "36", "West Bengal": "19", "Punjab": "03",
    "Rajasthan": "08", "Madhya Pradesh": "23", "Kerala": "32",
    "Odisha": "21", "Andhra Pradesh": "37", "Bihar": "10",
}

CONTACT_FIRST = [
    "Rajesh", "Suresh", "Mahesh", "Pradeep", "Amit", "Vikram", "Sanjay",
    "Ravi", "Arun", "Kiran", "Priya", "Neha", "Pooja", "Anita", "Kavita",
    "Dinesh", "Ramesh", "Nilesh", "Jignesh", "Kamlesh", "Bhavesh", "Hitesh",
    "Dipesh", "Chirag", "Hardik", "Vishal", "Rohan", "Nikhil", "Rahul",
    "Siddharth", "Vijay", "Ajay", "Manoj", "Sunil", "Kapil", "Naresh",
    "Deepak", "Ashok", "Pankaj", "Girish", "Manish", "Rakesh", "Hemant",
    "Lalit", "Vivek", "Gaurav", "Neeraj", "Tarun", "Arvind", "Santosh",
]

CONTACT_LAST = [
    "Shah", "Patel", "Mehta", "Desai", "Joshi", "Trivedi", "Pandya",
    "Parekh", "Kapoor", "Sharma", "Gupta", "Verma", "Singh", "Kumar",
    "Reddy", "Rao", "Nair", "Menon", "Pillai", "Iyer", "Krishnan",
    "Naidu", "Choudhary", "Agarwal", "Jain", "Bansal", "Mittal", "Goel",
    "Sethia", "Modi", "Thakkar", "Bhatt", "Raval", "Panchal", "Chauhan",
    "Solanki", "Rana", "Parikh", "Vyas", "Brahmbhatt",
]

CURRENT_YEAR    = datetime.now().year
APPROVED_DATE   = datetime(CURRENT_YEAR - 1, 4, 1)


def _gst(state: str, idx: int) -> str:
    code  = GST_STATES.get(state, "24")
    alpha = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    mid   = f"{alpha[idx % 26]}{alpha[(idx * 3) % 26]}{alpha[(idx * 7) % 26]}{alpha[(idx * 11) % 26]}{alpha[(idx * 13) % 26]}"
    num5  = str(random.randint(1000, 9999))
    return f"{code}{mid}{num5}Z{alpha[(idx * 17) % 26]}"


def _pan(idx: int) -> str:
    alpha = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return (f"{alpha[idx % 26]}{alpha[(idx*3)%26]}"
            f"{alpha[(idx*7)%26]}{alpha[(idx*11)%26]}"
            f"{alpha[(idx*13)%26]}"
            f"{str(random.randint(1000,9999))}"
            f"{alpha[(idx*17)%26]}")


def _email(name: str, idx: int) -> str:
    slug    = name.lower().replace(" ", "").replace(".", "")[:20]
    domains = ["gmail.com", "outlook.com", "yahoo.co.in",
               "business.com", "company.co.in", "info.in"]
    return f"{slug}{idx}@{random.choice(domains)}"


def _phone(idx: int) -> str:
    prefixes = ["98", "97", "96", "95", "94", "93", "92", "91", "90", "89", "88", "87"]
    return f"+91-{random.choice(prefixes)}{str(random.randint(10000000, 99999999))}"


def _sap_code(idx: int) -> str:
    return f"SAP{str(idx).zfill(6)}"


def build_vendor_pool() -> list:
    """Build a deterministic-ish pool of 1050+ vendor dicts."""
    pool = []
    idx  = 0

    def add(company, category, vtype, oem_approved=False, oem_brand=None,
            msme=False, city_tuple=None):
        nonlocal idx
        idx += 1
        if city_tuple is None:
            # Weight Gujarat cities heavily (Matrix Comsec is local)
            weights = ([0] * 10) + list(range(10, len(INDIAN_CITIES)))
            city_tuple = INDIAN_CITIES[idx % len(INDIAN_CITIES)]

        city, state, pin = city_tuple
        perf = round(random.uniform(35.0, 97.0), 2)

        # OEM-approved vendors tend to perform better
        if oem_approved:
            perf = round(random.uniform(60.0, 97.0), 2)

        pool.append(dict(
            vendor_code     = f"VEN-{str(idx).zfill(4)}",
            company_name    = company,
            contact_person  = f"{random.choice(CONTACT_FIRST)} {random.choice(CONTACT_LAST)}",
            email           = _email(company, idx),
            phone           = _phone(idx),
            address         = f"{random.randint(1,999)}, {company} Building, Industrial Area",
            city            = city,
            state           = state,
            pincode         = pin,
            country         = "India",
            category        = category,
            vendor_type     = vtype,
            oem_approved    = oem_approved,
            oem_brand       = oem_brand,
            gst_number      = _gst(state, idx),
            pan_number      = _pan(idx),
            msme_registered = msme,
            status          = "Approved",
            approved_by     = "Bhavesh",
            approved_at     = APPROVED_DATE,
            performance_score = perf,
            sap_vendor_code = _sap_code(idx),
            created_by      = "seed_script",
        ))

    # ── Electronic OEMs & Distributors (high-trust) ────────────
    for brand in OEM_BRANDS:
        city_t = random.choice(INDIAN_CITIES[:10])   # prefer Gujarat
        add(f"{brand} India Pvt Ltd", "Electronic", "OEM",
            oem_approved=True, oem_brand=brand, msme=False, city_tuple=city_t)
        add(f"{brand} Authorised Distributors", "Electronic", "Distributor",
            oem_approved=True, oem_brand=brand,
            msme=random.random() < 0.4, city_tuple=random.choice(INDIAN_CITIES[:10]))

    # ── Electronic companies (mix of cities) ────────────────────
    for i, company in enumerate(ELECTRONIC_COMPANIES):
        city_t = INDIAN_CITIES[i % len(INDIAN_CITIES)]
        brand  = random.choice(OEM_BRANDS) if random.random() < 0.5 else None
        vtype  = random.choice(["Distributor", "Distributor", "Trader", "OEM"])
        add(company, "Electronic", vtype,
            oem_approved=brand is not None and random.random() < 0.6,
            oem_brand=brand,
            msme=random.random() < 0.35,
            city_tuple=city_t)

    # ── Mechanical companies ────────────────────────────────────
    for i, company in enumerate(MECHANICAL_COMPANIES):
        city_t = INDIAN_CITIES[i % len(INDIAN_CITIES)]
        add(company, "Mechanical",
            random.choice(["Distributor", "Trader", "Trader"]),
            msme=random.random() < 0.55,
            city_tuple=city_t)

    # ── Both category ───────────────────────────────────────────
    for i, company in enumerate(BOTH_COMPANIES):
        city_t = INDIAN_CITIES[i % len(INDIAN_CITIES)]
        brand  = random.choice(OEM_BRANDS) if random.random() < 0.3 else None
        add(company, "Both", "Distributor",
            oem_approved=brand is not None,
            oem_brand=brand,
            msme=random.random() < 0.3,
            city_tuple=city_t)

    # ── Service vendors ─────────────────────────────────────────
    for i, company in enumerate(SERVICE_COMPANIES):
        city_t = random.choice(INDIAN_CITIES[:12])
        add(company, "Electronic", "Service", msme=True, city_tuple=city_t)

    # ── Fill up to 1050 with additional generated names ──────────
    suffixes = ["Enterprises", "Pvt Ltd", "India", "Tech", "Hub",
                "Systems", "Solutions", "Group", "Corporation", "Co."]

    while len(pool) < 1050:
        cat    = random.choice(["Electronic", "Electronic", "Mechanical", "Both"])
        brand  = random.choice(OEM_BRANDS) if cat == "Electronic" and random.random() < 0.35 else None
        vtype  = random.choice(
            ["OEM", "Distributor", "Distributor", "Distributor", "Trader"]
            if cat == "Electronic" else ["Distributor", "Trader", "Trader"]
        )
        city_t = random.choice(INDIAN_CITIES)
        name   = (
            f"{random.choice(CONTACT_FIRST)}{random.choice(CONTACT_LAST)} "
            f"{random.choice(suffixes)}"
        )
        add(name, cat, vtype,
            oem_approved=brand is not None and random.random() < 0.5,
            oem_brand=brand,
            msme=random.random() < 0.4,
            city_tuple=city_t)

    random.shuffle(pool)
    return pool


def seed_vendors():
    db   = SessionLocal()
    pool = build_vendor_pool()

    print(f"\n🔄  Seeding {len(pool)} vendors into s2p_matrix database...")
    inserted  = 0
    skipped   = 0
    errors    = 0

    # Grab existing emails to skip duplicates
    existing_emails = {row[0] for row in db.query(Vendor.email).all()}
    existing_codes  = {row[0] for row in db.query(Vendor.vendor_code).all()}

    BATCH = 100
    for start in range(0, len(pool), BATCH):
        batch = pool[start:start + BATCH]
        for vd in batch:
            if vd["email"] in existing_emails:
                skipped += 1
                continue
            if vd["vendor_code"] in existing_codes:
                # re-generate code
                count = db.query(Vendor).count() + inserted + 1
                vd["vendor_code"] = f"VEN-{str(count).zfill(4)}"
                if vd["vendor_code"] in existing_codes:
                    skipped += 1
                    continue

            try:
                vendor = Vendor(**vd)
                db.add(vendor)
                existing_emails.add(vd["email"])
                existing_codes.add(vd["vendor_code"])
                inserted += 1
            except Exception as e:
                errors += 1
                db.rollback()
                continue

        try:
            db.commit()
            print(f"  ✅  Batch {start // BATCH + 1}: "
                  f"{min(start + BATCH, len(pool))}/{len(pool)} processed")
        except Exception as e:
            db.rollback()
            print(f"  ❌  Batch commit error: {e}")

    print(f"\n📊  Result: {inserted} inserted | {skipped} skipped | {errors} errors")

    # ── Seed historical performance records ──────────────────────
    seed_performance(db, inserted)

    db.close()
    print("\n✅  Vendor seeding complete!\n")


def seed_performance(db: Session, vendor_count: int):
    """Add Q1–Q4 2025 performance records for all approved vendors."""
    periods = ["Q1-2025", "Q2-2025", "Q3-2025", "Q4-2025"]
    vendors = db.query(Vendor).filter(Vendor.status == "Approved").all()
    print(f"\n🔄  Seeding performance records for {len(vendors)} vendors × {len(periods)} periods...")

    inserted = 0
    for v in vendors:
        base_score = float(v.performance_score or 65.0)
        for period in periods:
            exists = db.query(VendorPerformance).filter(
                VendorPerformance.vendor_id        == v.id,
                VendorPerformance.evaluation_period == period
            ).first()
            if exists:
                continue

            # Simulate quarterly variance ±8 points
            variance = random.uniform(-8.0, 8.0)
            overall  = round(max(20.0, min(100.0, base_score + variance)), 2)

            delivery = round(max(20.0, min(100.0, overall + random.uniform(-10, 10))), 2)
            quality  = round(max(20.0, min(100.0, overall + random.uniform(-8, 8))),  2)
            pricing  = round(max(20.0, min(100.0, overall + random.uniform(-12, 12))), 2)
            response = round(max(20.0, min(100.0, overall + random.uniform(-6, 6))),  2)

            total_orders = random.randint(0, 25)
            on_time      = int(total_orders * (delivery / 100))
            rejected     = random.randint(0, max(0, total_orders // 10))
            rfqs_recv    = random.randint(1, 15)
            rfqs_resp    = int(rfqs_recv * (response / 100))

            perf = VendorPerformance(
                vendor_id          = v.id,
                evaluation_period  = period,
                delivery_score     = delivery,
                quality_score      = quality,
                pricing_score      = pricing,
                response_score     = response,
                overall_score      = overall,
                total_orders       = total_orders,
                on_time_deliveries = on_time,
                quality_rejections = rejected,
                rfqs_received      = rfqs_recv,
                rfqs_responded     = rfqs_resp,
                evaluated_at       = datetime.utcnow(),
                notes              = f"Auto-seeded historical record for {period}"
            )
            db.add(perf)
            inserted += 1

        if inserted % 500 == 0 and inserted > 0:
            db.commit()
            print(f"  ✅  {inserted} performance records committed...")

    db.commit()
    print(f"  ✅  {inserted} performance records seeded")


if __name__ == "__main__":
    random.seed(42)   # reproducible data
    seed_vendors()
