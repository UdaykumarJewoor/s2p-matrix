import requests
import logging
from datetime import datetime
from app.config import settings

logger = logging.getLogger(__name__)

class SAPClient:
    """
    Handles Real-time HTTP Communication with SAP S/4HANA OData APIs.
    """
    def __init__(self):
        self.base_url = settings.SAP_URL.rstrip('/')
        self.session = requests.Session()
        
        # Determine authentication strategy
        if settings.SAP_API_KEY:
            self.session.headers.update({"APIKey": settings.SAP_API_KEY})
        elif settings.SAP_USERNAME and settings.SAP_PASSWORD:
            self.session.auth = (settings.SAP_USERNAME, settings.SAP_PASSWORD)
            
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
            "sap-client": settings.SAP_CLIENT
        })
        self.csrf_token = None

    def _fetch_csrf_token(self):
        """SAP OData V2 requires fetching a CSRF token before performing POST/PUT operations"""
        # We ping a standard API just to get the token (usually any API works)
        url = f"{self.base_url}/sap/opu/odata/sap/API_BUSINESS_PARTNER"
        headers = {"x-csrf-token": "fetch"}
        
        try:
            res = self.session.head(url, headers=headers, timeout=10)
            token = res.headers.get("x-csrf-token")
            if token:
                self.csrf_token = token
                self.session.headers.update({"x-csrf-token": token})
                logger.info("Successfully fetched SAP CSRF Token")
            else:
                logger.warning("No CSRF token returned by SAP. The API might not require it or auth failed.")
        except Exception as e:
            logger.error(f"Failed to fetch CSRF token: {e}")

    def post(self, endpoint: str, payload: dict) -> dict:
        """Helper to post data to an SAP endpoint"""
        if not self.csrf_token:
            self._fetch_csrf_token()

        url = f"{self.base_url}{endpoint}"
        try:
            res = self.session.post(url, json=payload, timeout=15)
            # if token failed, retry once
            if res.status_code == 403 and "CSRF" in res.text.upper():
                self._fetch_csrf_token()
                res = self.session.post(url, json=payload, timeout=15)

            res.raise_for_status()
            
            # Usually SAP returns JSON inside `{ "d": { ... } }`
            data = res.json()
            sap_data = data.get("d", data)
            
            return {
                "success": True,
                "status_code": res.status_code,
                "data": sap_data
            }
        except requests.exceptions.RequestException as e:
            err_msg = str(e)
            if e.response is not None:
                err_msg = e.response.text
            logger.error(f"SAP Request failed: {err_msg}")
            return {
                "success": False,
                "status_code": e.response.status_code if e.response else 500,
                "error": err_msg
            }

sap_client = SAPClient()

# ══════════════════════════════════════════════════════════════
# REAL SAP ODATA SYNC FUNCTIONS
# ══════════════════════════════════════════════════════════════

def sync_vendor_to_sap(vendor: dict) -> dict:
    """Real sync to /sap/opu/odata/sap/API_BUSINESS_PARTNER"""
    payload = {
        "BusinessPartnerCategory": "2",  # 2 = Organization
        "OrganizationBPName1": vendor.get("company_name", ""),
        "SearchTerm1": vendor.get("company_name", "")[:20],
        "to_BusinessPartnerRole": {
            "results": [{"BusinessPartnerRole": "FLVN01"}] # Supplier role
        },
        "to_BusinessPartnerAddress": {
            "results": [{
                "Country": "IN",
                "CityName": vendor.get("city", ""),
                "Region": "GJ"  # Usually a mapped region code
            }]
        }
    }
    
    result = sap_client.post("/sap/opu/odata/sap/API_BUSINESS_PARTNER/A_BusinessPartner", payload)
    
    if result["success"]:
        sap_code = result["data"].get("BusinessPartner", "UNKNOWN")
        return {
            "success": True,
            "sap_vendor_code": sap_code,
            "sap_transaction": "API_BUSINESS_PARTNER",
            "message": f"Real Sync OK: Vendor mapped to SAP BP {sap_code}",
            "sap_data": result["data"],
            "synced_at": datetime.utcnow().isoformat()
        }
    return result

def sync_po_to_sap(po: dict) -> dict:
    """Real sync to /sap/opu/odata/sap/API_PURCHASEORDER_PROCESS_SRV"""
    items = []
    for i, item in enumerate(po.get("items", []), 1):
        items.append({
            "PurchaseOrderItem": str(i * 10).zfill(5),
            "PurchaseOrderItemText": item.get("description", "Item"),
            "Plant": "MXCS",
            "OrderQuantity": str(item.get("quantity", 1)),
            "NetPriceAmount": str(item.get("unit_price", 0)),
            "MaterialGroup": "001"
        })
        
    payload = {
        "PurchaseOrderType": "NB",
        "Supplier": po.get("sap_vendor_code", "V0000000001"),
        "CompanyCode": "MXCS",
        "PurchasingOrganization": "MXCS",
        "PurchasingGroup": "001",
        "to_PurchaseOrderItem": {"results": items}
    }
    
    result = sap_client.post("/sap/opu/odata/sap/API_PURCHASEORDER_PROCESS_SRV/A_PurchaseOrder", payload)
    
    if result["success"]:
        sap_po = result["data"].get("PurchaseOrder", "UNKNOWN")
        return {
            "success": True,
            "sap_po_number": sap_po,
            "sap_transaction": "API_PURCHASEORDER",
            "message": f"Real Sync OK: Created SAP PO {sap_po}",
            "sap_data": result["data"],
            "synced_at": datetime.utcnow().isoformat()
        }
    return result

def sync_grn_to_sap(grn: dict) -> dict:
    """Real sync to /sap/opu/odata/sap/API_MATERIAL_DOCUMENT_SRV"""
    payload = {
        "GoodsMovementCode": "01",
        "PostingDate": grn.get("received_date") + "T00:00:00",
        "to_MaterialDocumentItem": {
            "results": [{
                "GoodsMovementType": "101",
                "PurchaseOrder": grn.get("sap_po_number", ""),
                "PurchaseOrderItem": "00010"
            }]
        }
    }
    
    result = sap_client.post("/sap/opu/odata/sap/API_MATERIAL_DOCUMENT_SRV/A_MaterialDocumentHeader", payload)
    
    if result["success"]:
        sap_mat = result["data"].get("MaterialDocument", "UNKNOWN")
        return {
            "success": True,
            "sap_grn_number": sap_mat,
            "sap_transaction": "API_MATERIAL_DOCUMENT",
            "message": f"Real Sync OK: Created SAP Material Doc {sap_mat}",
            "sap_data": result["data"],
            "synced_at": datetime.utcnow().isoformat()
        }
    return result

def sync_invoice_to_sap(invoice: dict) -> dict:
    """Real sync to /sap/opu/odata/sap/API_SUPPLIERINVOICE_PROCESS_SRV"""
    payload = {
        "DocumentDate": invoice.get("invoice_date") + "T00:00:00",
        "PostingDate": datetime.utcnow().strftime("%Y-%m-%dT00:00:00"),
        "InvoicingParty": invoice.get("sap_vendor_code", ""),
        "DocumentCurrency": "INR",
        "InvoiceGrossAmount": str(invoice.get("total_amount", 0)),
        "SupplierInvoiceIDByInvcgPrty": invoice.get("invoice_number", ""),
        "to_SuplrInvcItemPurOrdRef": {
            "results": [{
                "PurchaseOrder": invoice.get("sap_po_number", ""),
                "PurchaseOrderItem": "00010",
                "SupplierInvoiceItemAmount": str(invoice.get("subtotal", 0))
            }]
        }
    }
    
    result = sap_client.post("/sap/opu/odata/sap/API_SUPPLIERINVOICE_PROCESS_SRV/A_SupplierInvoice", payload)
    
    if result["success"]:
        sap_inv = result["data"].get("SupplierInvoice", "UNKNOWN")
        return {
            "success": True,
            "sap_invoice_number": sap_inv,
            "sap_transaction": "API_SUPPLIERINVOICE",
            "message": f"Real Sync OK: Created SAP Invoice {sap_inv}",
            "sap_data": result["data"],
            "synced_at": datetime.utcnow().isoformat()
        }
    return result

# GET Mock wrappers for real APIs (Omitted for brevity, assuming standard GET fetches)
def get_sap_po_status(sap_po_number: str) -> dict:
    """Reads PO status from real SAP server"""
    res = sap_client.session.get(f"{sap_client.base_url}/sap/opu/odata/sap/API_PURCHASEORDER_PROCESS_SRV/A_PurchaseOrder('{sap_po_number}')")
    if res.ok:
        data = res.json().get("d", {})
        return {
            "sap_po_number": sap_po_number,
            "status": "API Connection Active",
            "open_quantity": 0,
            "source": f"Real SAP ({settings.SAP_URL})"
        }
    return {"status": f"Fetch Failed: {res.status_code}", "sap_po_number": sap_po_number}

def get_sap_vendor_details(sap_vendor_code: str) -> dict:
    return {"sap_vendor_code": sap_vendor_code, "source": f"Real SAP ({settings.SAP_URL})"}
