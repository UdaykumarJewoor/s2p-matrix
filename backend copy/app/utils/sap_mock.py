# utils/sap_mock.py
# SAP S/4HANA MM Mock Integration Layer (NFR-01)
# Simulates real SAP API calls — swap with real SAP endpoints later
# Supports: Vendor Master, Purchase Orders, GRN, Invoice

from datetime import datetime
import random
import string

def generate_sap_id(prefix: str) -> str:
    """Generate a fake SAP document number"""
    num = ''.join(random.choices(string.digits, k=10))
    return f"{prefix}{num}"

# ══════════════════════════════════════════════════════════════
# VENDOR MASTER SYNC (Transaction: XK01 / MK01)
# ══════════════════════════════════════════════════════════════
def sync_vendor_to_sap(vendor: dict) -> dict:
    """
    Simulate pushing a vendor to SAP Vendor Master.
    In production: POST to SAP /sap/opu/odata/sap/API_BUSINESS_PARTNER
    """
    sap_vendor_code = generate_sap_id("V")

    return {
        "success"        : True,
        "sap_vendor_code": sap_vendor_code,
        "sap_transaction": "XK01",
        "message"        : f"Vendor '{vendor.get('company_name')}' created in SAP as {sap_vendor_code}",
        "sap_data": {
            "Supplier"          : sap_vendor_code,
            "SupplierName"      : vendor.get("company_name"),
            "Country"           : "IN",
            "Region"            : vendor.get("state", "GJ"),
            "City"              : vendor.get("city"),
            "TaxNumber1"        : vendor.get("gst_number"),
            "CompanyCode"       : "MXCS",              # Matrix Comsec company code
            "PurchasingOrg"     : "MXCS",
            "PaymentTerms"      : "NT30",
            "AccountGroup"      : "KRED",
        },
        "synced_at": datetime.utcnow().isoformat()
    }

# ══════════════════════════════════════════════════════════════
# PURCHASE ORDER SYNC (Transaction: ME21N)
# ══════════════════════════════════════════════════════════════
def sync_po_to_sap(po: dict) -> dict:
    """
    Simulate creating a PO in SAP MM.
    In production: POST to SAP /sap/opu/odata/sap/API_PURCHASEORDER_PROCESS_SRV
    """
    sap_po_number = generate_sap_id("45")   # SAP PO numbers start with 45

    items = []
    for i, item in enumerate(po.get("items", []), 1):
        items.append({
            "PurchaseOrderItem"    : str(i * 10).zfill(5),  # 00010, 00020...
            "PurchaseOrderItemText": item.get("description"),
            "Plant"                : "MXCS",
            "StorageLocation"      : "0001",
            "OrderQuantity"        : str(item.get("quantity", 1)),
            "OrderPriceUnit"       : item.get("unit", "EA"),
            "NetPriceAmount"       : str(item.get("unit_price", 0)),
            "TaxCode"              : "V5",              # 18% GST code
            "MaterialGroup"        : "001",
        })

    return {
        "success"      : True,
        "sap_po_number": sap_po_number,
        "sap_transaction": "ME21N",
        "message"      : f"PO {po.get('po_number')} synced to SAP as {sap_po_number}",
        "sap_data": {
            "PurchaseOrder"         : sap_po_number,
            "PurchaseOrderType"     : "NB",           # Standard PO
            "Supplier"              : po.get("sap_vendor_code", "V0000000001"),
            "CompanyCode"           : "MXCS",
            "PurchasingOrganization": "MXCS",
            "PurchasingGroup"       : "001",
            "DocumentDate"          : po.get("po_date"),
            "CreationDate"          : datetime.utcnow().date().isoformat(),
            "to_PurchaseOrderItem"  : {"results": items}
        },
        "synced_at": datetime.utcnow().isoformat()
    }

# ══════════════════════════════════════════════════════════════
# GOODS RECEIPT (Transaction: MIGO)
# ══════════════════════════════════════════════════════════════
def sync_grn_to_sap(grn: dict) -> dict:
    """
    Simulate posting a Goods Receipt in SAP MM.
    In production: POST to SAP /sap/opu/odata/sap/API_MATERIAL_DOCUMENT_SRV
    """
    sap_grn = generate_sap_id("50")   # Material docs start with 50

    return {
        "success"       : True,
        "sap_grn_number": sap_grn,
        "sap_transaction": "MIGO",
        "message"       : f"GRN {grn.get('grn_number')} posted in SAP as Material Doc {sap_grn}",
        "sap_data": {
            "MaterialDocumentYear"  : str(datetime.now().year),
            "MaterialDocument"      : sap_grn,
            "GoodsMovementCode"     : "01",        # GR against PO
            "PurchaseOrder"         : grn.get("sap_po_number", ""),
            "PostingDate"           : grn.get("received_date"),
            "DocumentDate"          : grn.get("received_date"),
            "GoodsMovementType"     : "101",       # GR for PO
        },
        "synced_at": datetime.utcnow().isoformat()
    }

# ══════════════════════════════════════════════════════════════
# INVOICE VERIFICATION (Transaction: MIRO)
# ══════════════════════════════════════════════════════════════
def sync_invoice_to_sap(invoice: dict) -> dict:
    """
    Simulate posting Logistics Invoice Verification in SAP MM.
    In production: POST to SAP /sap/opu/odata/sap/API_LOGICALNTWK_SRV
    """
    sap_inv = generate_sap_id("51")   # Invoice doc numbers

    return {
        "success"           : True,
        "sap_invoice_number": sap_inv,
        "sap_transaction"   : "MIRO",
        "message"           : f"Invoice {invoice.get('invoice_number')} posted in SAP as {sap_inv}",
        "sap_data": {
            "FiscalYear"               : str(datetime.now().year),
            "LogicalInvoiceDocument"   : sap_inv,
            "InvoicingParty"           : invoice.get("sap_vendor_code", ""),
            "DocumentDate"             : invoice.get("invoice_date"),
            "PostingDate"              : datetime.utcnow().date().isoformat(),
            "InvoiceGrossAmount"       : str(invoice.get("total_amount", 0)),
            "DocumentCurrency"         : "INR",
            "TaxAmount"                : str(invoice.get("tax_amount", 0)),
            "PurchaseOrder"            : invoice.get("sap_po_number", ""),
            "SupplierInvoiceIDByInvcgPrty": invoice.get("invoice_number"),
        },
        "synced_at": datetime.utcnow().isoformat()
    }

# ══════════════════════════════════════════════════════════════
# READ FROM SAP (Simulate GET calls)
# ══════════════════════════════════════════════════════════════
def get_sap_po_status(sap_po_number: str) -> dict:
    """Simulate reading PO status from SAP"""
    statuses = ["Open", "Partially Delivered", "Fully Delivered", "Closed"]
    return {
        "sap_po_number": sap_po_number,
        "status"       : random.choice(statuses),
        "open_quantity": random.randint(0, 100),
        "source"       : "SAP S/4HANA MM (Mock)"
    }

def get_sap_vendor_details(sap_vendor_code: str) -> dict:
    """Simulate reading vendor master from SAP"""
    return {
        "sap_vendor_code"  : sap_vendor_code,
        "payment_terms"    : "NT30",
        "withholding_tax"  : "194C",
        "account_group"    : "KRED",
        "company_code"     : "MXCS",
        "purchasing_org"   : "MXCS",
        "source"           : "SAP S/4HANA MM (Mock)"
    }

def health_check() -> dict:
    """Simulate SAP system health check"""
    return {
        "sap_system"  : "S4H",
        "client"      : "100",
        "environment" : "Development (Mock)",
        "status"      : "Connected",
        "version"     : "SAP S/4HANA 2023",
        "modules"     : ["MM", "FI-AP"],
        "checked_at"  : datetime.utcnow().isoformat()
    }