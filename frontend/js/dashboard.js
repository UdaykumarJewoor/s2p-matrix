// dashboard.js v3.0 — BR-S2P-08 Commercial Governance Dashboard
document.addEventListener("DOMContentLoaded", async () => {

  // ── Date ──────────────────────────────────────────────────────
  const d = new Date();
  document.getElementById("today-date").textContent =
    d.toLocaleDateString("en-IN", { weekday: "short", day: "2-digit",
                                     month: "short", year: "numeric" });

  // ── 1. Core KPIs ──────────────────────────────────────────────
  try {
    const data = await api.get("/dashboard/summary");

    document.getElementById("kpi-vendors").textContent   = data.vendors.total;
    document.getElementById("kpi-approved").textContent  = data.vendors.approved;
    document.getElementById("kpi-rfq").textContent       = data.rfq.open;
    document.getElementById("kpi-po").textContent        = data.purchase_orders.total;
    document.getElementById("kpi-unmatched").textContent = data.invoices.unmatched;
    document.getElementById("kpi-spend").textContent     = formatINR(data.purchase_orders.total_spend_inr);

    // Pending Approvals panel
    const approvalBox = document.getElementById("pending-approvals");
    const pendingPO   = data.purchase_orders.pending_approval;
    const pendingVen  = data.vendors.pending;

    if (pendingPO === 0 && pendingVen === 0) {
      approvalBox.innerHTML = `<div class="empty-state">
        <i class="fa fa-check-circle"></i><p>No pending approvals 🎉</p></div>`;
    } else {
      approvalBox.innerHTML = `
        <table class="data-table">
          <thead><tr><th>Item</th><th>Count</th><th>Action</th></tr></thead>
          <tbody>
            <tr>
              <td><i class="fa fa-shopping-cart" style="color:var(--orange)"></i> Purchase Orders</td>
              <td><span class="badge badge-pending">${pendingPO}</span></td>
              <td><a href="pages/purchase_orders.html" class="btn btn-outline" style="padding:5px 12px;font-size:12px">View</a></td>
            </tr>
            <tr>
              <td><i class="fa fa-building" style="color:var(--blue)"></i> New Vendors</td>
              <td><span class="badge badge-pending">${pendingVen}</span></td>
              <td><a href="pages/vendors.html" class="btn btn-outline" style="padding:5px 12px;font-size:12px">View</a></td>
            </tr>
          </tbody>
        </table>`;
    }

    // Invoice Exceptions panel
    const invBox    = document.getElementById("invoice-exceptions");
    const unmatched = data.invoices.unmatched;
    const unpaid    = data.invoices.unpaid;

    if (unmatched === 0 && unpaid === 0) {
      invBox.innerHTML = `<div class="empty-state">
        <i class="fa fa-check-circle"></i><p>All invoices are clean ✅</p></div>`;
    } else {
      invBox.innerHTML = `
        <table class="data-table">
          <thead><tr><th>Type</th><th>Count</th><th>Amount</th></tr></thead>
          <tbody>
            <tr>
              <td><i class="fa fa-exclamation-triangle" style="color:var(--red)"></i> Unmatched Invoices</td>
              <td><span class="badge badge-mismatch">${unmatched}</span></td>
              <td>—</td>
            </tr>
            <tr>
              <td><i class="fa fa-clock" style="color:var(--orange)"></i> Unpaid Invoices</td>
              <td><span class="badge badge-pending">${unpaid}</span></td>
              <td>${formatINR(data.invoices.unpaid_amount_inr)}</td>
            </tr>
          </tbody>
        </table>`;
    }
  } catch (err) {
    console.error("Dashboard summary error:", err);
    showToast("Failed to load dashboard data. Is the server running?", "error");
  }

  // ── 2. BR-S2P-08: Commercial Governance ───────────────────────
  try {
    const gov = await api.get("/governance/governance-summary");

    // KPI Strip
    const s = gov.summary;
    document.getElementById("gov-planned").textContent  = formatINR(s.total_planned_inr);
    document.getElementById("gov-actual").textContent   = formatINR(s.total_actual_inr);
    document.getElementById("gov-ebit").textContent     = formatINR(gov.ebit.ebit_savings_inr);
    document.getElementById("gov-ebit-pct").textContent = gov.ebit.ebit_margin_pct + "%";

    // Budget vs Actual chart
    renderBudgetChart(gov.category_spend);

    // Category detail table
    renderCategoryTable(gov.category_spend);

    // Top Vendor Spend Table
    renderVendorSpendTable(gov.vendor_allocation);

  } catch (err) {
    console.error("Governance error:", err);
    document.getElementById("gov-planned").textContent  = "N/A";
    document.getElementById("gov-actual").textContent   = "N/A";
    document.getElementById("gov-ebit").textContent     = "N/A";
    document.getElementById("gov-ebit-pct").textContent = "N/A";
  }

  // ── 3. Negotiation Savings Chart + Insights ───────────────────
  try {
    const s = await api.get("/negotiations/summary");
    document.getElementById("avg-savings-pct").textContent = s.avg_savings_percent + "%";
    renderInsights(s);
    initSavingsChart();
  } catch (e) {
    console.error("Negotiation Stats Error:", e);
  }
});


// ── Budget vs Actual Bar Chart ───────────────────────────────────
function renderBudgetChart(categoryData) {
  const ctx = document.getElementById("budgetChart").getContext("2d");

  if (!categoryData || categoryData.length === 0) {
    ctx.font = "14px Inter"; ctx.textAlign = "center"; ctx.fillStyle = "#94a3b8";
    ctx.fillText("No category spend data yet.", ctx.canvas.width / 2, ctx.canvas.height / 2);
    return;
  }

  const labels   = categoryData.map(c => c.category);
  const planned  = categoryData.map(c => c.planned_inr);
  const actual   = categoryData.map(c => c.actual_inr);

  new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "Planned Budget (INR)",
          data: planned,
          backgroundColor: "rgba(59,130,246,0.25)",
          borderColor: "#3b82f6",
          borderWidth: 2,
          borderRadius: 8,
        },
        {
          label: "Actual Spend (INR)",
          data: actual,
          backgroundColor: "rgba(34,197,94,0.35)",
          borderColor: "#22c55e",
          borderWidth: 2,
          borderRadius: 8,
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      scales: {
        y: {
          beginAtZero: true,
          ticks: {
            callback: v => "₹" + (v >= 100000 ? (v/100000).toFixed(1) + "L" : v.toLocaleString("en-IN")),
            font: { size: 12 }
          },
          grid: { color: "rgba(0,0,0,0.05)" }
        },
        x: { ticks: { font: { size: 13, weight: "600" } } }
      },
      plugins: {
        legend: { position: "top", labels: { usePointStyle: true, boxWidth: 8, font: { size: 13 } } },
        tooltip: {
          callbacks: {
            label: ctx => ` ${ctx.dataset.label}: ₹${Number(ctx.raw).toLocaleString("en-IN")}`
          }
        }
      }
    }
  });
}


// ── Category Detail Table ────────────────────────────────────────
function renderCategoryTable(categoryData) {
  const el = document.getElementById("category-detail-table");
  if (!categoryData || categoryData.length === 0) { el.innerHTML = ""; return; }

  el.innerHTML = `
    <table class="data-table" style="margin-top:12px;">
      <thead>
        <tr>
          <th>Category</th>
          <th style="text-align:right;">Budget (INR)</th>
          <th style="text-align:right;">Actual (INR)</th>
          <th style="text-align:right;">Utilisation</th>
          <th style="text-align:right;">Variance</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        ${categoryData.map(c => `
          <tr>
            <td><strong>${c.category}</strong></td>
            <td style="text-align:right;">₹${Number(c.planned_inr).toLocaleString("en-IN")}</td>
            <td style="text-align:right;">₹${Number(c.actual_inr).toLocaleString("en-IN")}</td>
            <td style="text-align:right;">
              <div style="display:flex;align-items:center;gap:6px;justify-content:flex-end;">
                <div style="width:60px;height:6px;background:#e2e8f0;border-radius:3px;overflow:hidden;">
                  <div style="width:${Math.min(c.utilisation_pct,100)}%;height:100%;background:${c.utilisation_pct>100?'#ef4444':c.utilisation_pct>80?'#f59e0b':'#22c55e'};border-radius:3px;"></div>
                </div>
                <span style="font-weight:700;color:${c.utilisation_pct>100?'#ef4444':c.utilisation_pct>80?'#d97706':'#16a34a'};">${c.utilisation_pct}%</span>
              </div>
            </td>
            <td style="text-align:right;color:${c.variance_inr>=0?'#16a34a':'#ef4444'};font-weight:600;">
              ${c.variance_inr>=0?'+':''}₹${Math.abs(c.variance_inr).toLocaleString("en-IN")}
            </td>
            <td>
              <span style="font-size:11px;font-weight:700;padding:3px 8px;border-radius:99px;${c.status==='Over Budget'?'background:#fee2e2;color:#991b1b':'background:#dcfce7;color:#166534'}">
                ${c.status}
              </span>
            </td>
          </tr>`).join("")}
      </tbody>
    </table>`;
}


// ── Top Vendor Spend Table ───────────────────────────────────────
function renderVendorSpendTable(vendors) {
  const el = document.getElementById("vendor-spend-table");

  if (!vendors || vendors.length === 0) {
    el.innerHTML = `<div style="text-align:center;padding:30px;color:var(--text-muted);">
      <i class="fa fa-box-open fa-2x" style="margin-bottom:10px;display:block;"></i>No vendor spend data yet.
    </div>`;
    return;
  }

  el.innerHTML = `
    <table class="data-table">
      <thead>
        <tr>
          <th>#</th>
          <th>Vendor</th>
          <th>Cat.</th>
          <th style="text-align:right;">Spend (INR)</th>
          <th style="text-align:right;">Share</th>
        </tr>
      </thead>
      <tbody>
        ${vendors.map((v, i) => `
          <tr>
            <td style="font-weight:800;color:var(--text-muted);font-size:12px;">${i + 1}</td>
            <td>
              <div style="font-weight:700;font-size:13px;color:var(--primary);">${v.vendor_name}</div>
              <div style="font-size:10px;color:var(--text-muted);">${v.vendor_type} · ${v.po_count} PO(s)</div>
            </td>
            <td><span style="font-size:11px;background:#eff6ff;color:#1d4ed8;padding:2px 7px;border-radius:99px;font-weight:600;">${v.category}</span></td>
            <td style="text-align:right;font-weight:700;">₹${Number(v.spend_inr).toLocaleString("en-IN")}</td>
            <td style="text-align:right;">
              <div style="display:flex;align-items:center;gap:5px;justify-content:flex-end;">
                <div style="width:48px;height:5px;background:#e2e8f0;border-radius:3px;overflow:hidden;">
                  <div style="width:${v.share_pct}%;height:100%;background:#3b82f6;border-radius:3px;"></div>
                </div>
                <span style="font-size:12px;font-weight:600;color:#1d4ed8;">${v.share_pct}%</span>
              </div>
            </td>
          </tr>`).join("")}
      </tbody>
    </table>`;
}


// ── Procurement Value Realization Chart (Monthly Savings) ────────
async function initSavingsChart() {
  try {
    const data = await api.get("/negotiations/chart-data/");
    const ctx  = document.getElementById("savingsChart").getContext("2d");

    if (!data.labels || !data.labels.length) {
      ctx.font = "14px Inter"; ctx.textAlign = "center"; ctx.fillStyle = "#94a3b8";
      ctx.fillText("No savings data available yet.", ctx.canvas.width / 2, ctx.canvas.height / 2);
      return;
    }

    new Chart(ctx, {
      type: "bar",
      data: {
        labels: data.labels,
        datasets: [
          {
            label: "Savings (INR)",
            data: data.savings,
            backgroundColor: "rgba(34,197,94,0.1)",
            borderColor: "#22c55e",
            borderWidth: 3,
            type: "line",
            pointRadius: 6,
            tension: 0.4,
            yAxisID: "y"
          },
          {
            label: "Initial Value",
            data: data.initial,
            backgroundColor: "rgba(59,130,246,0.25)",
            borderRadius: 8,
            yAxisID: "y1"
          },
          {
            label: "Agreed Value",
            data: data.agreed,
            backgroundColor: "rgba(147,51,234,0.25)",
            borderRadius: 8,
            yAxisID: "y1"
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        scales: {
          y: {
            type: "linear", display: true, position: "right",
            title: { display: true, text: "Savings (INR)", font: { size: 12, weight: "bold" } },
            ticks: { font: { size: 11 } },
            grid: { drawOnChartArea: false }
          },
          y1: {
            type: "linear", display: true, position: "left",
            title: { display: true, text: "Total Value (INR)", font: { size: 12, weight: "bold" } },
            ticks: { font: { size: 11 } }
          },
          x: { ticks: { font: { size: 12, weight: "600" } } }
        },
        plugins: {
          legend: { position: "top", labels: { usePointStyle: true, boxWidth: 8, font: { size: 12 } } }
        }
      }
    });
  } catch (e) {
    console.error("Savings chart error:", e);
  }
}


// ── Negotiation Insights ─────────────────────────────────────────
function renderInsights(s) {
  const container = document.getElementById("neg-insight-container");
  if (!container) return;
  const status = s.total_savings_inr > 100000 ? "Excellent" : "On Track";
  container.innerHTML = `
    <div style="font-size:14px;line-height:1.6;">
      <div style="margin-bottom:12px;"><strong>Status:</strong>
        <span style="color:var(--green)">${status} Performance</span>
      </div>
      <div style="margin-bottom:12px;">You have achieved <strong>${formatINR(s.total_savings_inr)}</strong>
        in direct cost avoidance this period.</div>
      <div style="padding:12px;background:rgba(59,130,246,0.05);border-radius:8px;font-size:13px;color:var(--primary);">
        <i class="fa fa-info-circle"></i>
        Negotiation efficiency is trending at <strong>${s.avg_savings_percent}%</strong>
        reduction vs. market quotes.
      </div>
    </div>`;
}