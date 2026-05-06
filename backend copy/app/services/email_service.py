# services/email_service.py
# RFQ Email Dispatch — Matrix Comsec S2P Platform
#
# EMAIL_MODE = "simulate"  -> Logs email to console (default, no SMTP needed)
# EMAIL_MODE = "smtp"      -> Sends real email via SMTP (only to @yopmail.com during testing)
#
# To enable real email: set in .env
#   EMAIL_MODE=smtp
#   SMTP_HOST=smtp.gmail.com
#   SMTP_PORT=587
#   SMTP_USER=your@email.com
#   SMTP_PASS=yourpassword
#   SMTP_FROM=noreply@matrixcomsec.com
#   PLATFORM_URL=https://yourplatform.com

import os
import secrets
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────
EMAIL_MODE   = os.getenv("EMAIL_MODE",   "simulate")   # "simulate" or "smtp"
SMTP_HOST    = os.getenv("SMTP_HOST",    "smtp.gmail.com")
SMTP_PORT    = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER    = os.getenv("SMTP_USER",    "")
SMTP_PASS    = os.getenv("SMTP_PASS",    "")
SMTP_FROM    = os.getenv("SMTP_FROM",    "noreply@matrixcomsec.com")
PLATFORM_URL = os.getenv("PLATFORM_URL", "http://127.0.0.1:5500/frontend/pages")


# ── Token Generation ────────────────────────────────────────────

def generate_vendor_token() -> str:
    """Generate a cryptographically secure 48-char URL-safe token."""
    return secrets.token_urlsafe(36)


def get_token_expiry(deadline) -> datetime:
    """Token expires 2 days after RFQ deadline."""
    from datetime import date
    if isinstance(deadline, date):
        return datetime.combine(deadline, datetime.min.time()) + timedelta(days=2)
    return datetime.utcnow() + timedelta(days=30)


# ── Email Builder ───────────────────────────────────────────────

def _build_rfq_email_html(
    vendor_name: str,
    contact_person: str,
    rfq_number: str,
    rfq_title: str,
    deadline: str,
    items: list,
    portal_link: str
) -> str:
    items_rows = "".join(
        f"<tr>"
        f"<td style='padding:8px 12px;border-bottom:1px solid #e2e8f0;font-size:13px;color:#64748b;vertical-align:top;'>{i+1}</td>"
        f"<td style='padding:8px 12px;border-bottom:1px solid #e2e8f0;font-size:13px;font-weight:600;color:#1e293b;vertical-align:top;'>{item.get('description','')}</td>"
        f"<td style='padding:8px 12px;border-bottom:1px solid #e2e8f0;font-size:13px;text-align:center;color:#1e293b;vertical-align:top;'>{item.get('quantity','')} {item.get('unit','PCS')}</td>"
        f"</tr>"
        for i, item in enumerate(items)
    )

    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>RFQ Invitation - {rfq_number}</title>
</head>
<body style="margin:0;padding:0;background-color:#f1f5f9;font-family:Arial,Helvetica,sans-serif;">

<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#f1f5f9;padding:32px 16px;">
<tr><td align="center">

  <table width="600" cellpadding="0" cellspacing="0" border="0"
         style="background-color:#ffffff;border-radius:12px;overflow:hidden;">

    <!-- HEADER BANNER -->
    <tr>
      <td style="background-color:#1e3a5f;padding:28px 32px;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0">
          <tr>
            <td>
              <span style="font-size:22px;font-weight:800;color:#ffffff;letter-spacing:-0.5px;">
                HG INFO TECH &mdash; S2P Platform
              </span><br/>
              <span style="font-size:13px;color:rgba(255,255,255,0.7);">
                Matrix Comsec Pvt. Ltd. &mdash; Procurement Automation
              </span>
            </td>
          </tr>
        </table>
      </td>
    </tr>

    <!-- BODY -->
    <tr>
      <td style="padding:32px;">

        <h2 style="font-size:20px;font-weight:700;color:#1e293b;margin:0 0 8px;">
          You have received a Request for Quotation
        </h2>
        <p style="font-size:14px;color:#64748b;margin:0 0 24px;line-height:1.7;">
          Dear <strong style="color:#1e293b;">{contact_person or vendor_name}</strong>,<br/><br/>
          <strong style="color:#1e293b;">Matrix Comsec Pvt. Ltd.</strong> invites you to submit a
          competitive quotation for the following procurement requirement. Please review the details
          and submit your best quote before the deadline shown below.
        </p>

        <!-- RFQ DETAILS BOX -->
        <table width="100%" cellpadding="0" cellspacing="0" border="0"
               style="background-color:#f8fafc;border-radius:8px;border:1px solid #e2e8f0;margin-bottom:24px;">
          <tr>
            <td style="padding:18px 20px;">
              <table width="100%" cellpadding="5" cellspacing="0" border="0" style="font-size:14px;">
                <tr>
                  <td style="color:#64748b;width:160px;">RFQ Number</td>
                  <td style="font-weight:700;color:#1e293b;">{rfq_number}</td>
                </tr>
                <tr>
                  <td style="color:#64748b;">Requirement</td>
                  <td style="font-weight:600;color:#1e293b;">{rfq_title}</td>
                </tr>
                <tr>
                  <td style="color:#64748b;">Submission Deadline</td>
                  <td style="font-weight:700;color:#dc2626;">{deadline}</td>
                </tr>
                <tr>
                  <td style="color:#64748b;">Vendor</td>
                  <td style="color:#1e293b;">{vendor_name}</td>
                </tr>
              </table>
            </td>
          </tr>
        </table>

        <!-- ITEMS TABLE -->
        <p style="font-size:14px;font-weight:700;color:#1e293b;margin:0 0 10px;">
          Items Required
        </p>
        <table width="100%" cellpadding="0" cellspacing="0" border="0"
               style="border-collapse:collapse;border:1px solid #e2e8f0;margin-bottom:28px;">
          <thead>
            <tr style="background-color:#f1f5f9;">
              <th style="padding:10px 12px;text-align:left;font-size:12px;font-weight:700;
                         color:#64748b;text-transform:uppercase;border-bottom:2px solid #e2e8f0;
                         width:40px;">#</th>
              <th style="padding:10px 12px;text-align:left;font-size:12px;font-weight:700;
                         color:#64748b;text-transform:uppercase;border-bottom:2px solid #e2e8f0;">
                Description</th>
              <th style="padding:10px 12px;text-align:center;font-size:12px;font-weight:700;
                         color:#64748b;text-transform:uppercase;border-bottom:2px solid #e2e8f0;
                         width:120px;">Quantity</th>
            </tr>
          </thead>
          <tbody>
            {items_rows}
          </tbody>
        </table>

        <!-- ACTION REQUIRED PANEL -->
        <table width="100%" cellpadding="0" cellspacing="0" border="0"
               style="background-color:#eff6ff;border:2px solid #1a56db;border-radius:10px;margin-bottom:20px;">
          <tr>
            <td style="padding:22px 24px;">
              <p style="font-size:16px;font-weight:700;color:#1e3a5f;margin:0 0 6px;">
                ACTION REQUIRED: Submit Your Quotation
              </p>
              <p style="font-size:13px;color:#1d4ed8;margin:0 0 18px;line-height:1.6;">
                Click the button below to open the secure Vendor Quotation Portal
                where you can enter your pricing and submit your bid.
              </p>

              <!-- TABLE-BASED CTA BUTTON — works in all email clients -->
              <table cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td align="center" bgcolor="#1a56db"
                      style="border-radius:8px;background-color:#1a56db;">
                    <a href="{portal_link}"
                       target="_blank"
                       style="display:inline-block;padding:15px 36px;
                              font-size:16px;font-weight:700;
                              color:#ffffff;text-decoration:none;
                              letter-spacing:0.5px;
                              font-family:Arial,Helvetica,sans-serif;
                              background-color:#1a56db;border-radius:8px;">
                      OPEN VENDOR PORTAL &amp; SUBMIT QUOTE
                    </a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
        </table>

        <!-- FALLBACK LINK BOX -->
        <table width="100%" cellpadding="0" cellspacing="0" border="0"
               style="background-color:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;margin-bottom:24px;">
          <tr>
            <td style="padding:14px 18px;">
              <p style="font-size:12px;font-weight:700;color:#64748b;margin:0 0 6px;
                        text-transform:uppercase;letter-spacing:0.5px;">
                If the button above does not open, copy and paste this link into your browser:
              </p>
              <p style="font-size:12px;color:#1a56db;word-break:break-all;margin:0;
                        font-family:monospace,Courier,sans-serif;">
                {portal_link}
              </p>
            </td>
          </tr>
        </table>

        <!-- SECURITY NOTE -->
        <p style="font-size:12px;color:#94a3b8;text-align:center;margin:0 0 20px;">
          This link is unique to your company and expires 2 days after the submission deadline.<br/>
          Do <strong>NOT</strong> share this link with anyone else.
        </p>

        <hr style="border:none;border-top:1px solid #e2e8f0;margin:20px 0;"/>

        <p style="font-size:12px;color:#94a3b8;margin:0;line-height:1.6;">
          This is an automated notification from the HG Info Tech S2P Procurement Platform.<br/>
          For queries, contact:
          <a href="mailto:procurement@matrixcomsec.com"
             style="color:#1a56db;text-decoration:none;">
            procurement@matrixcomsec.com
          </a>
        </p>

      </td>
    </tr>

    <!-- FOOTER -->
    <tr>
      <td style="background-color:#f8fafc;padding:16px 32px;border-top:1px solid #e2e8f0;">
        <p style="font-size:11px;color:#cbd5e1;text-align:center;margin:0;">
          Matrix Comsec Pvt. Ltd. &mdash; S2P Procurement Platform &mdash; Confidential
        </p>
      </td>
    </tr>

  </table>

</td></tr>
</table>

</body>
</html>
"""


# ── Dispatch Functions ─────────────────────────────────────────

def send_rfq_invitation(
    vendor_email: str,
    vendor_name: str,
    contact_person: str,
    rfq_number: str,
    rfq_title: str,
    deadline: str,
    items: list,
    token: str
) -> dict:
    """
    Send RFQ invitation email to a single vendor.
    Returns dict with status and portal_link.

    In simulate mode: logs to console, no SMTP required.
    In smtp mode: sends real email (only dispatches to @yopmail.com for safe testing).
    """
    portal_link = f"{PLATFORM_URL}/vendor_portal.html?token={token}"

    html_body = _build_rfq_email_html(
        vendor_name=vendor_name,
        contact_person=contact_person,
        rfq_number=rfq_number,
        rfq_title=rfq_title,
        deadline=deadline,
        items=items,
        portal_link=portal_link
    )
    subject = f"RFQ Invitation: {rfq_number} - {rfq_title} | Matrix Comsec Procurement"

    if EMAIL_MODE == "smtp" and vendor_email.lower().endswith("@yopmail.com"):
        return _send_smtp(vendor_email, subject, html_body, portal_link)
    else:
        return _send_simulated(vendor_email, vendor_name, rfq_number, portal_link)


def _send_simulated(
    vendor_email: str,
    vendor_name: str,
    rfq_number: str,
    portal_link: str
) -> dict:
    """Simulate email dispatch - logs to console. No SMTP needed."""
    logger.info(
        f"\n{'='*65}\n"
        f"[SIMULATED EMAIL] RFQ Invitation\n"
        f"   To     : {vendor_email} ({vendor_name})\n"
        f"   Subject: RFQ {rfq_number} - Quotation Invitation\n"
        f"   Link   : {portal_link}\n"
        f"{'='*65}"
    )
    print(
        f"\n[EMAIL SIMULATED]\n"
        f"   To: {vendor_email}\n"
        f"   RFQ: {rfq_number}\n"
        f"   Portal: {portal_link}\n"
    )
    return {
        "status"     : "simulated",
        "to"         : vendor_email,
        "portal_link": portal_link,
        "message"    : "Email simulated (set EMAIL_MODE=smtp in .env for real sending)"
    }


def _send_smtp(
    to_email: str,
    subject: str,
    html_body: str,
    portal_link: str
) -> dict:
    """Send real email via SMTP."""
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = SMTP_FROM
        msg["To"]      = to_email
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            if SMTP_USER and SMTP_PASS:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_FROM, to_email, msg.as_string())

        logger.info(f"Email sent successfully to {to_email}")
        return {
            "status"     : "sent",
            "to"         : to_email,
            "portal_link": portal_link,
            "message"    : "Email sent successfully"
        }
    except Exception as e:
        logger.error(f"Email failed to {to_email}: {e}")
        return {
            "status"     : "failed",
            "to"         : to_email,
            "portal_link": portal_link,
            "error"      : str(e)
        }


# ── PO Notification Email ───────────────────────────────────────

def send_po_to_vendor(
    vendor_email: str,
    vendor_name: str,
    contact_person: str,
    po_id: int,
    po_number: str,
    po_date: str,
    delivery_date: str,
    payment_terms: str,
    delivery_address: str,
    items: list,
    subtotal: float,
    tax_amount: float,
    total_amount: float,
    notes: str = ""
) -> dict:
    """Send a Purchase Order award notification email to the vendor."""

    items_rows = "".join(
        f"<tr>"
        f"<td style='padding:8px 12px;border-bottom:1px solid #e2e8f0;font-size:13px;color:#64748b;'>{i+1}</td>"
        f"<td style='padding:8px 12px;border-bottom:1px solid #e2e8f0;font-size:13px;font-weight:600;color:#1e293b;'>{item.get('description','')}</td>"
        f"<td style='padding:8px 12px;border-bottom:1px solid #e2e8f0;font-size:13px;text-align:center;'>{item.get('quantity','')}</td>"
        f"<td style='padding:8px 12px;border-bottom:1px solid #e2e8f0;font-size:13px;text-align:right;'>INR {float(item.get('unit_price',0)):,.2f}</td>"
        f"<td style='padding:8px 12px;border-bottom:1px solid #e2e8f0;font-size:13px;text-align:right;font-weight:700;'>INR {float(item.get('total_price',0)):,.2f}</td>"
        f"</tr>"
        for i, item in enumerate(items)
    )

    notes_section = f"""
    <table width="100%" cellpadding="0" cellspacing="0" border="0"
           style="background-color:#fefce8;border:1px solid #fde68a;border-radius:8px;margin-bottom:20px;">
      <tr><td style="padding:14px 18px;">
        <p style="font-size:12px;font-weight:700;color:#92400e;margin:0 0 4px;">Notes / Special Instructions:</p>
        <p style="font-size:13px;color:#78350f;margin:0;">{notes}</p>
      </td></tr>
    </table>""" if notes else ""

    html_body = f"""\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"/><title>Purchase Order - {po_number}</title></head>
<body style="margin:0;padding:0;background-color:#f1f5f9;font-family:Arial,Helvetica,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#f1f5f9;padding:32px 16px;">
<tr><td align="center">
<table width="620" cellpadding="0" cellspacing="0" border="0"
       style="background:#ffffff;border-radius:12px;overflow:hidden;">

  <!-- HEADER -->
  <tr>
    <td style="background-color:#1e3a5f;padding:24px 32px;">
      <table width="100%" cellpadding="0" cellspacing="0" border="0">
        <tr>
          <td>
            <span style="font-size:20px;font-weight:800;color:#ffffff;">MATRIX COMSEC PVT. LTD.</span><br/>
            <span style="font-size:12px;color:rgba(255,255,255,0.65);">Procurement Automation Platform</span>
          </td>
          <td align="right">
            <span style="font-size:18px;font-weight:800;color:#93c5fd;letter-spacing:1px;">PURCHASE ORDER</span>
          </td>
        </tr>
      </table>
    </td>
  </tr>

  <!-- AWARD BANNER -->
  <tr>
    <td style="background-color:#059669;padding:14px 32px;">
      <p style="font-size:15px;font-weight:700;color:#ffffff;margin:0;">
        Congratulations! You have been awarded this Purchase Order.
      </p>
      <p style="font-size:12px;color:rgba(255,255,255,0.8);margin:4px 0 0;">
        Please review the details below and confirm acceptance at your earliest convenience.
      </p>
    </td>
  </tr>

  <!-- BODY -->
  <tr>
    <td style="padding:28px 32px;">

      <p style="font-size:14px;color:#64748b;margin:0 0 20px;line-height:1.7;">
        Dear <strong style="color:#1e293b;">{contact_person or vendor_name}</strong>,<br/><br/>
        <strong style="color:#1e293b;">Matrix Comsec Pvt. Ltd.</strong> is pleased to issue this
        Purchase Order to <strong style="color:#1e293b;">{vendor_name}</strong>.
        Please acknowledge receipt and confirm your acceptance.
      </p>

      <!-- PO DETAILS BOX -->
      <table width="100%" cellpadding="0" cellspacing="0" border="0"
             style="background-color:#f8fafc;border-radius:8px;border:1px solid #e2e8f0;margin-bottom:24px;">
        <tr>
          <td style="padding:18px 20px;">
            <table width="100%" cellpadding="5" cellspacing="0" border="0" style="font-size:14px;">
              <tr>
                <td style="color:#64748b;width:160px;">PO Number</td>
                <td style="font-weight:800;color:#1e3a5f;font-size:16px;">{po_number}</td>
              </tr>
              <tr>
                <td style="color:#64748b;">PO Date</td>
                <td style="font-weight:600;color:#1e293b;">{po_date}</td>
              </tr>
              <tr>
                <td style="color:#64748b;">Expected Delivery</td>
                <td style="font-weight:700;color:#dc2626;">{delivery_date or 'To be confirmed'}</td>
              </tr>
              <tr>
                <td style="color:#64748b;">Payment Terms</td>
                <td style="color:#1e293b;">{payment_terms or 'As per agreement'}</td>
              </tr>
              <tr>
                <td style="color:#64748b;">Delivery Address</td>
                <td style="color:#1e293b;font-size:12px;">{delivery_address or 'Matrix Comsec, Gandhinagar'}</td>
              </tr>
            </table>
          </td>
        </tr>
      </table>

      <!-- ITEMS TABLE -->
      <p style="font-size:14px;font-weight:700;color:#1e293b;margin:0 0 10px;">Line Items</p>
      <table width="100%" cellpadding="0" cellspacing="0" border="0"
             style="border-collapse:collapse;border:1px solid #e2e8f0;margin-bottom:16px;">
        <thead>
          <tr style="background-color:#1e3a5f;">
            <th style="padding:10px 12px;text-align:left;font-size:11px;font-weight:700;color:#ffffff;width:30px;">#</th>
            <th style="padding:10px 12px;text-align:left;font-size:11px;font-weight:700;color:#ffffff;">Description</th>
            <th style="padding:10px 12px;text-align:center;font-size:11px;font-weight:700;color:#ffffff;width:60px;">Qty</th>
            <th style="padding:10px 12px;text-align:right;font-size:11px;font-weight:700;color:#ffffff;width:120px;">Unit Price</th>
            <th style="padding:10px 12px;text-align:right;font-size:11px;font-weight:700;color:#ffffff;width:120px;">Amount</th>
          </tr>
        </thead>
        <tbody>{items_rows}</tbody>
      </table>

      <!-- TOTALS -->
      <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:20px;">
        <tr>
          <td></td>
          <td width="260">
            <table width="100%" cellpadding="5" cellspacing="0" border="0"
                   style="font-size:13px;border-top:1px solid #e2e8f0;">
              <tr>
                <td style="color:#64748b;">Subtotal</td>
                <td style="text-align:right;font-weight:600;">INR {subtotal:,.2f}</td>
              </tr>
              <tr>
                <td style="color:#64748b;">Tax (GST)</td>
                <td style="text-align:right;font-weight:600;">INR {tax_amount:,.2f}</td>
              </tr>
              <tr style="border-top:2px solid #1e3a5f;">
                <td style="font-size:15px;font-weight:800;color:#1e3a5f;padding-top:8px;">Total</td>
                <td style="text-align:right;font-size:16px;font-weight:800;color:#1e3a5f;padding-top:8px;">INR {total_amount:,.2f}</td>
              </tr>
            </table>
          </td>
        </tr>
      </table>

      {notes_section}

      <!-- ACTION BOX -->
      <table width="100%" cellpadding="0" cellspacing="0" border="0"
             style="background-color:#eff6ff;border:2px solid #1a56db;border-radius:10px;margin-bottom:20px;">
        <tr>
          <td style="padding:18px 22px;">
            <p style="font-size:14px;font-weight:700;color:#1e3a5f;margin:0 0 6px;">
              ACTION REQUIRED: Acknowledge & View Purchase Order
            </p>
            <p style="font-size:13px;color:#1d4ed8;margin:0 0 16px;line-height:1.5;">
              Please click the button below to view the official Purchase Order document (PDF format). Confirm acceptance by replying to this email.
            </p>
            <!-- CTA BUTTON -->
            <table cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td align="center" bgcolor="#1a56db" style="border-radius:8px;">
                  <a href="{PLATFORM_URL}/po_template.html?po_id={po_id}" target="_blank"
                     style="display:inline-block;padding:12px 24px;font-size:14px;font-weight:700;color:#ffffff;text-decoration:none;letter-spacing:0.5px;font-family:Arial,sans-serif;background-color:#1a56db;border-radius:8px;">
                    VIEW PO DOCUMENT
                  </a>
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>

      <hr style="border:none;border-top:1px solid #e2e8f0;margin:20px 0;"/>

      <p style="font-size:12px;color:#94a3b8;margin:0;line-height:1.6;">
        This is an official Purchase Order from Matrix Comsec Pvt. Ltd.<br/>
        For queries: <a href="mailto:procurement@matrixcomsec.com" style="color:#1a56db;text-decoration:none;">procurement@matrixcomsec.com</a>
      </p>
    </td>
  </tr>

  <!-- FOOTER -->
  <tr>
    <td style="background-color:#f8fafc;border-top:1px solid #e2e8f0;padding:14px 32px;text-align:center;">
      <p style="font-size:11px;color:#cbd5e1;margin:0;">
        Matrix Comsec Pvt. Ltd. &mdash; Plot No. 12, Electronic Estate, Gandhinagar - 382 021, Gujarat, India
      </p>
    </td>
  </tr>

</table>
</td></tr>
</table>
</body>
</html>"""

    subject = f"Purchase Order {po_number} — Matrix Comsec Pvt. Ltd."

    if EMAIL_MODE == "smtp" and vendor_email.lower().endswith("@yopmail.com"):
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"]    = SMTP_FROM
            msg["To"]      = vendor_email
            msg.attach(MIMEText(html_body, "html"))
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                if SMTP_USER and SMTP_PASS:
                    server.starttls()
                    server.login(SMTP_USER, SMTP_PASS)
                server.sendmail(SMTP_FROM, vendor_email, msg.as_string())
            logger.info(f"PO email sent to {vendor_email}")
            return {"status": "sent", "to": vendor_email, "message": f"PO {po_number} emailed to {vendor_email}"}
        except Exception as e:
            logger.error(f"PO email failed: {e}")
            return {"status": "failed", "to": vendor_email, "error": str(e)}
    else:
        print(f"\n[PO EMAIL SIMULATED] {po_number} -> {vendor_email}\n")
        return {"status": "simulated", "to": vendor_email, "message": f"PO email simulated for {vendor_email}"}

