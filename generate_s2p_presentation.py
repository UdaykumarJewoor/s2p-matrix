import asyncio
from playwright.async_api import async_playwright
from fpdf import FPDF
import time
import os

pdf = FPDF(orientation="L", unit="mm", format="A4")

slides = [
    {
        "title": "Source-to-Pay (S2P) Workflow Automation",
        "subtitle": "Building the Strategic Procurement Engine for Matrix Comsec Pvt. Ltd.",
        "text": [
            "Current State vs Future State:",
            " - Vendor Master: Google Sheets -> Centralized DB + SAP Sync",
            " - RFQ Evaluation: Manual spreadsheet -> Auto quotation comparison",
            " - Approvals & Governance: Lack of visibility -> Unified dashboard"
        ]
    },
    {
        "title": "Commercial Governance Dashboard (BR-S2P-08)",
        "subtitle": "Real-time EBIT Margin & Budget vs Actual Spend",
        "screenshot": "http://127.0.0.1:5500/frontend/index.html",
        "action": None
    },
    {
        "title": "AI Vendor Discovery (BR-S2P-01)",
        "subtitle": "Smart Vendor Scoring & OEM Qualification Engine",
        "screenshot": "http://127.0.0.1:5500/frontend/pages/ai_discovery.html",
        "action": "discovery" # click the button
    },
    {
        "title": "Dynamic Compliance Checklists (BR-S2P-12)",
        "subtitle": "Automated Review Cycles with Overdue Alerts",
        "screenshot": "http://127.0.0.1:5500/frontend/pages/checklists.html",
        "action": None
    },
    {
        "title": "Automated Workflow Pipeline (BR-S2P-15)",
        "subtitle": "1-Click Generation of Quotations, POs, GRN & Invoices",
        "screenshot": "http://127.0.0.1:5500/frontend/pages/workflow.html",
        "action": "workflow" # trigger stages
    }
]

async def capture_screens():
    async with async_playwright() as p:
        # Launch browser headless
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()

        for idx, slide in enumerate(slides):
            if "screenshot" in slide:
                print(f"Navigating to {slide['screenshot']} ...")
                await page.goto(slide['screenshot'])
                await page.wait_for_timeout(2000) # let network requests and api calls settle
                
                # Perform any UI actions to show off features
                if slide["action"] == "discovery":
                    try:
                        # Click the Discover button
                        await page.evaluate("runDiscovery()")
                        await page.wait_for_timeout(3000)
                    except Exception as e:
                        print("Eval error:", e)
                elif slide["action"] == "workflow":
                    try:
                        await page.evaluate("runStage('stage_2')")
                        await page.wait_for_timeout(500)
                    except Exception as e:
                        print("Eval error:", e)
                
                # Take screenshot
                img_path = f"slide_{idx}.png"
                await page.screenshot(path=img_path)
                slide["img_path"] = img_path
                print(f"Saved {img_path}")
        
        await browser.close()

def build_pdf():
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_font("Arial", "", "C:\\Windows\\Fonts\\arial.ttf", uni=True)
    pdf.add_font("Arial", "B", "C:\\Windows\\Fonts\\arialbd.ttf", uni=True)

    for slide in slides:
        pdf.add_page()
        
        # Background color
        pdf.set_fill_color(248, 250, 252) # light slate
        pdf.rect(0, 0, 297, 210, "F")
        
        # Header banner
        pdf.set_fill_color(15, 118, 110) # primary teal
        pdf.rect(0, 0, 297, 30, "F")
        
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Arial", "B", 20)
        pdf.set_xy(15, 10)
        pdf.cell(0, 10, slide["title"], ln=True)
        
        pdf.set_font("Arial", "", 12)
        pdf.set_xy(15, 20)
        pdf.cell(0, 5, slide["subtitle"], ln=True)
        
        pdf.set_text_color(15, 23, 42)
        
        if "img_path" in slide and os.path.exists(slide["img_path"]):
            pdf.image(slide["img_path"], x=10, y=35, w=277)
        elif "text" in slide:
            pdf.set_xy(15, 50)
            pdf.set_font("Arial", "", 16)
            for line in slide["text"]:
                pdf.cell(0, 10, line, ln=True)

    output_path = "Matrix_Comsec_S2P_Presentation.pdf"
    pdf.output(output_path)
    print(f"PDF successfully generated at: {os.path.abspath(output_path)}")

async def main():
    print("Capturing screens...")
    await capture_screens()
    print("Building PDF...")
    build_pdf()

if __name__ == "__main__":
    asyncio.run(main())
