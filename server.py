import json
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import uvicorn

from db import get_conn, init_db, reset_demo_db
from sentinel import (
    compute_account_health,
    create_and_vault_live_sandbox_order,
     paypal_client,
    run_autonomous_freeze_defuser,
    trigger_friendly_fraud_auto_defense,
    trigger_viral_flash_sale,
)

init_db(seed_initial=True)
app = FastAPI(title="ZeroHold // Proactive Seller Protection & Freeze-Prevention Platform")


@app.get("/api/state")
async def api_state() -> dict:
    return compute_account_health()


@app.post("/api/simulate/flash-sale")
async def api_flash_sale() -> dict:
    return trigger_viral_flash_sale()


@app.post("/api/simulate/defuse-freeze")
async def api_defuse_freeze() -> dict:
    return run_autonomous_freeze_defuser()


@app.post("/api/simulate/friendly-fraud")
async def api_friendly_fraud() -> dict:
    return trigger_friendly_fraud_auto_defense()


@app.post("/api/simulate/live-sandbox-order")
async def api_live_sandbox() -> dict:
    return create_and_vault_live_sandbox_order()


@app.get("/api/paypal/order/{order_id}")
async def api_verify_order_on_paypal(order_id: str) -> dict:
    """Fetches the live Order object directly from https://api-m.sandbox.paypal.com."""
    return paypal_client.fetch_live_order_from_paypal(order_id)


@app.get("/api/dossier/latest/report", response_class=HTMLResponse)
async def api_printable_dossier_report() -> HTMLResponse:
    """Renders a printable/downloadable Official PayPal Underwriting Pre-Freeze Dossier."""
    conn = get_conn()
    row = conn.execute("SELECT * FROM legitimacy_dossiers ORDER BY created_at DESC LIMIT 1").fetchone()
    conn.close()
    if not row:
        return HTMLResponse("<h3>No Dossier Generated Yet. Run the Autonomous Freeze Defuser first.</h3>")

    d = json.loads(row["dossier_json"])
    rows_html = "".join(
        f"""<tr class="border-b border-slate-300">
          <td class="p-2 font-mono font-bold">{item['paypal_order_id']}</td>
          <td class="p-2">{item['item_name']} (<code>{item['sku']}</code>)</td>
          <td class="p-2 font-bold">${item['amount_usd']:,.2f}</td>
          <td class="p-2 font-mono text-xs">{item['supplier_invoice_id']}<br/><span class="text-slate-500">{item['supplier_name']} (Cost: ${item['wholesale_cost_usd']:,.2f} | Bin: {item['warehouse_bin']})</span></td>
          <td class="p-2 font-mono text-xs font-bold text-emerald-800">{item['carrier']} #{item['tracking_number']}</td>
          <td class="p-2 font-mono text-xs">{item['paypal_server_stamp']}<br/><span class="text-slate-500">Debug-Id: {item['paypal_debug_id']}</span></td>
        </tr>"""
        for item in d.get("collated_orders", [])
    )

    return HTMLResponse(f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{d['dossier_id']} — PayPal Merchant Risk Underwriting Packet</title>
<script src="https://cdn.tailwindcss.com"></script></head>
<body class="bg-white text-slate-900 p-8 font-sans max-w-6xl mx-auto space-y-6">
  <div class="flex justify-between items-start border-b-2 border-slate-900 pb-4">
    <div>
      <div class="text-xs font-mono uppercase tracking-widest text-slate-500">PROACTIVE MERCHANT UNDERWRITING SUBMISSION</div>
      <h1 class="text-2xl font-bold mt-1">PayPal Pre-Freeze Account Legitimacy &amp; Fulfillment Dossier</h1>
      <p class="text-sm text-slate-600">Dossier ID: <strong>{d['dossier_id']}</strong> | Generated: {d.get('generated_at_iso', '')}</p>
    </div>
    <button onclick="window.print()" class="bg-slate-900 text-white px-4 py-2 rounded text-xs font-bold hover:bg-slate-700">
      Print / Save as PDF
    </button>
  </div>

  <div class="grid grid-cols-3 gap-4 bg-slate-100 p-4 rounded border border-slate-300 text-sm">
    <div><span class="text-slate-500 block text-xs">Velocity Trigger Event</span><strong>{d['headline']}</strong></div>
    <div><span class="text-slate-500 block text-xs">Freeze Risk Mitigation</span><strong class="text-emerald-700">{d['freeze_risk_drop']}</strong></div>
    <div><span class="text-slate-500 block text-xs">Verified Wholesale Inventory Basis</span><strong>${d.get('total_wholesale_inventory_verified_usd', 0):,.2f} USD (100% In-Stock)</strong></div>
  </div>

  <div>
    <h2 class="text-sm font-bold uppercase tracking-wider mb-2">1. Order-by-Order Supplier Invoice &amp; Live PayPal Waybill Reconciliation</h2>
    <table class="w-full text-left border border-slate-300 text-sm">
      <thead class="bg-slate-200 text-xs uppercase">
        <tr>
          <th class="p-2">PayPal Order ID</th>
          <th class="p-2">Item &amp; SKU</th>
          <th class="p-2">Capture</th>
          <th class="p-2">Distributor Invoice &amp; Warehouse Bin</th>
          <th class="p-2">Synced Waybill</th>
          <th class="p-2">PayPal Server Stamp &amp; Debug-Id</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>
  </div>
</body></html>""")


@app.post("/api/reset")
async def api_reset() -> dict:
    reset_demo_db()
    return compute_account_health()


@app.get("/", response_class=HTMLResponse)
async def cockpit_ui() -> HTMLResponse:
    return HTMLResponse("""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>ZeroHold // PayPal Seller Protection & Freeze-Cliff Command Center</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdn.jsdelivr.net/npm/ag-grid-community@31.3.2/dist/ag-grid-community.min.js"></script>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/ag-grid-community@31.3.2/styles/ag-grid.css" />
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/ag-grid-community@31.3.2/styles/ag-theme-quartz.css" />
  <style>
    body { background: #090d16; color: #f1f5f9; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }
    .ag-theme-quartz-dark {
      --ag-background-color: #0f172a;
      --ag-header-background-color: #1e293b;
      --ag-odd-row-background-color: #0b1120;
      --ag-row-hover-color: #1e293b;
      --ag-border-color: #334155;
      --ag-value-change-value-highlight-background-color: #10b98166;
      --ag-font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      --ag-font-size: 12px;
    }
  </style>
</head>
<body class="p-5">
  <div class="max-w-[1460px] mx-auto space-y-5">

    <!-- Top Header -->
    <div class="flex flex-wrap justify-between items-center border-b border-slate-800 pb-4 gap-3">
      <div>
        <div class="flex items-center gap-3">
          <span class="text-xl font-bold text-emerald-400 tracking-tight">ZEROHOLD</span>
          <span class="text-xs bg-emerald-950 border border-emerald-700 text-emerald-300 px-2.5 py-0.5 rounded font-semibold">
            Zero-Touch Friendly Fraud Vault &amp; Pre-Freeze Account Sentinel
          </span>
        </div>
        <p class="text-xs text-slate-400 mt-1">
          Powered by <strong class="text-cyan-300">APIMatic PayPal Python Server SDK (v2.4.0)</strong> + <strong class="text-amber-300">AG Grid</strong> + <strong class="text-emerald-300">Live PayPal Sandbox Orders &amp; Disputes APIs</strong>
        </p>
      </div>
      <div class="flex items-center gap-2">
        <span id="sdkBadge" class="text-xs px-3 py-1.5 rounded border border-slate-700 bg-slate-900 text-cyan-300">
          Checking APIMatic SDK...
        </span>
        <button onclick="runAction('/api/reset')" class="text-xs bg-slate-800 hover:bg-slate-700 border border-slate-600 px-3 py-1.5 rounded text-slate-200">
          Reset Demo (Mints Real Sandbox Orders)
        </button>
      </div>
    </div>

    <!-- 4 Live Telemetry Gauges -->
    <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
      <div id="freezeCard" class="border border-slate-800 bg-slate-900/80 p-4 rounded-lg space-y-1">
        <div class="text-[11px] text-slate-400 uppercase">Account Freeze Risk Score</div>
        <div id="freezeScore" class="text-2xl font-bold text-emerald-400">-- / 100</div>
        <div id="freezeState" class="text-[11px] font-bold text-emerald-300">--</div>
      </div>

      <div class="border border-slate-800 bg-slate-900/80 p-4 rounded-lg space-y-1">
        <div class="text-[11px] text-slate-400 uppercase">24h GMV Velocity (Welford Z-Score)</div>
        <div id="gmvValue" class="text-2xl font-bold text-cyan-400">$0.00</div>
        <div id="gmvSub" class="text-[11px] text-slate-400">Baseline: $4,000/day</div>
      </div>

      <div class="border border-slate-800 bg-slate-900/80 p-4 rounded-lg space-y-1">
        <div class="text-[11px] text-slate-400 uppercase">Seller-Protected Volume</div>
        <div id="protectedValue" class="text-2xl font-bold text-emerald-400">100%</div>
        <div id="untrackedSub" class="text-[11px] text-slate-400">0 Untracked Captures</div>
      </div>

      <div class="border border-slate-800 bg-slate-900/80 p-4 rounded-lg space-y-1">
        <div class="text-[11px] text-slate-400 uppercase">Dispute Ratio vs. 1.50% Freeze Cliff</div>
        <div id="disputeValue" class="text-2xl font-bold text-sky-400">0.86%</div>
        <div class="text-[11px] text-slate-400">PayPal &amp; Visa VAMP Limit: 1.50%</div>
      </div>
    </div>

    <!-- Interactive Demo Action Bar -->
    <div class="border border-slate-800 bg-slate-900/60 p-3.5 rounded-lg flex flex-wrap items-center justify-between gap-3">
      <div class="flex flex-wrap gap-2.5">
        <button onclick="runAction('/api/simulate/flash-sale')"
          class="text-xs font-bold bg-amber-500 hover:bg-amber-400 text-slate-950 px-3.5 py-2 rounded shadow">
          1. Simulate 4.6x Flash-Sale Spike (Mints 5 Real Sandbox Orders &rarr; 83.1 Freeze Risk)
        </button>
        <button onclick="runAction('/api/simulate/defuse-freeze')"
          class="text-xs font-bold bg-emerald-500 hover:bg-emerald-400 text-slate-950 px-3.5 py-2 rounded shadow">
          2. Run Autonomous Freeze Defuser (Batch Track + Collate Underwriting Dossier)
        </button>
        <button onclick="runAction('/api/simulate/friendly-fraud')"
          class="text-xs font-bold bg-rose-600 hover:bg-rose-500 text-white px-3.5 py-2 rounded shadow">
          3. Fire $800 Friendly Fraud Webhook (Zero-Touch Auto-Defense)
        </button>
        <button onclick="runAction('/api/simulate/live-sandbox-order')"
          class="text-xs font-bold bg-cyan-500 hover:bg-cyan-400 text-slate-950 px-3.5 py-2 rounded shadow">
          + Create 1 Live Sandbox Order (APIMatic SDK)
        </button>
      </div>
      <div class="flex items-center gap-2">
        <input id="quickFilter" oninput="onQuickFilter()" type="text" placeholder="Filter AG Grid (Order ID, SKU, PO)..."
          class="text-xs bg-slate-950 border border-slate-700 rounded px-3 py-1.5 text-slate-200 w-56" />
        <button onclick="exportCsv()" class="text-xs bg-slate-800 hover:bg-slate-700 border border-slate-700 px-3 py-1.5 rounded text-cyan-300">
          Export Vault CSV
        </button>
      </div>
    </div>

    <!-- AG Grid Order Evidence Vault -->
    <div class="space-y-2">
      <div class="flex justify-between items-center">
        <h2 class="text-xs font-bold uppercase tracking-wider text-slate-300">
          AG Grid Continuous Order Evidence Vault (With Pinned Totals, Cell Flash, &amp; Live PayPal Server Verification)
        </h2>
        <span id="statusSpinner" class="text-xs text-amber-400 font-bold hidden animate-pulse">
          Executing Live HTTPS Calls to api-m.sandbox.paypal.com...
        </span>
      </div>
      <div id="vaultGrid" class="ag-theme-quartz-dark w-full h-[360px] rounded-lg border border-slate-800"></div>
    </div>

    <!-- Bottom Dual Inspector -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div class="border border-slate-800 bg-slate-900/70 p-4 rounded-lg space-y-3">
        <div class="flex justify-between items-center border-b border-slate-800 pb-2">
          <span class="text-xs font-bold text-cyan-400 uppercase">
            Collated Pre-Freeze Underwriting Dossier &amp; Order Forensic Vault
          </span>
          <a id="printableDossierBtn" href="/api/dossier/latest/report" target="_blank"
            class="hidden text-[11px] bg-emerald-600 hover:bg-emerald-500 text-slate-950 font-bold px-2.5 py-1 rounded">
            Open Printable Underwriting Packet &nearr;
          </a>
        </div>
        <div id="dossierPanel" class="text-xs text-slate-300 space-y-3 max-h-[310px] overflow-y-auto pr-1"></div>
      </div>

      <div class="border border-slate-800 bg-slate-900/70 p-4 rounded-lg space-y-3">
        <div class="text-xs font-bold text-emerald-400 uppercase border-b border-slate-800 pb-2">
          Live Outbound APIMatic SDK &amp; PayPal Sandbox Stream (With Paypal-Debug-Id)
        </div>
        <div id="auditLogPanel" class="space-y-2 max-h-[310px] overflow-y-auto pr-1 text-[11px]"></div>
      </div>
    </div>

  </div>

  <!-- Live PayPal Sandbox Server Verification Modal -->
  <div id="paypalModal" class="fixed inset-0 bg-black/80 hidden items-center justify-center p-6 z-50">
    <div class="bg-slate-900 border border-cyan-700 rounded-lg max-w-3xl w-full p-5 space-y-3">
      <div class="flex justify-between items-center border-b border-slate-800 pb-2">
        <span id="modalTitle" class="text-sm font-bold text-cyan-300">Live Response from api-m.sandbox.paypal.com</span>
        <button onclick="closeModal()" class="text-xs bg-slate-800 px-2.5 py-1 rounded text-slate-300">Close</button>
      </div>
      <pre id="modalJson" class="bg-slate-950 p-3 rounded border border-slate-800 text-[11px] text-emerald-300 overflow-x-auto max-h-[420px]"></pre>
    </div>
  </div>

  <script>
    let gridApi = null;
    let latestState = null;

    const columnDefs = [
      { field: "order_id", headerName: "PayPal Order ID", width: 170, pinned: "left",
        cellClass: "font-bold text-cyan-300" },
      { field: "amount_usd", headerName: "Amount", width: 105, enableCellChangeFlash: true,
        valueFormatter: p => p.value !== undefined ? `$${Number(p.value).toFixed(2)}` : "",
        cellClass: "font-bold text-slate-100" },
      { field: "item_name", headerName: "Product & SKU", flex: 1, minWidth: 185,
        cellRenderer: p => p.node.rowPinned ? `<strong class="text-amber-300">${p.value}</strong>` : `<span>${p.value} <code class="text-[10px] text-slate-400">[${p.data.sku}]</code></span>` },
      { field: "supplier_invoice_id", headerName: "Supplier Invoice (Stock Proof)", width: 175,
        cellRenderer: p => p.node.rowPinned ? "" : `<span class="text-slate-300">${p.value} <span class="text-[10px] text-emerald-400">(${p.data.units_in_warehouse} in bin)</span></span>` },
      { field: "tracking_number", headerName: "Carrier & Waybill", width: 170, enableCellChangeFlash: true,
        cellRenderer: p => {
          if (p.node.rowPinned) return `<strong class="text-cyan-300">${p.value || ''}</strong>`;
          return p.value
            ? `<span class="text-emerald-300 font-bold">${p.data.carrier}: ${p.value}</span>`
            : `<span class="text-amber-400 font-bold animate-pulse">UNTRACKED BACKLOG</span>`;
        }
      },
      { field: "seller_protection", headerName: "Seller Protection", width: 160, enableCellChangeFlash: true,
        cellRenderer: p => {
          if (p.node.rowPinned) return "";
          return p.value === "ELIGIBLE_ACTIVE"
            ? `<span class="bg-emerald-950 border border-emerald-700 text-emerald-300 px-2 py-0.5 rounded text-[10px] font-bold">ELIGIBLE // ACTIVE</span>`
            : `<span class="bg-amber-950 border border-amber-700 text-amber-300 px-2 py-0.5 rounded text-[10px] font-bold">HOLD EXPOSURE</span>`;
        }
      },
      { field: "dispute_status", headerName: "Dispute Status", width: 165, enableCellChangeFlash: true,
        cellRenderer: p => {
          if (p.node.rowPinned) return "";
          if (p.value === "AUTO_DEFENDED_PROTECTED") {
            return `<span class="bg-emerald-900 text-emerald-200 px-2 py-0.5 rounded text-[10px] font-bold">AUTO-DEFENDED ($0)</span>`;
          }
          return `<span class="text-slate-500 text-[11px]">No Claim</span>`;
        }
      },
      { headerName: "Live PayPal Check", width: 145, pinned: "right",
        cellRenderer: p => {
          if (p.node.rowPinned) return "";
          return `<button onclick="verifyOrderOnPayPal('${p.data.order_id}')" class="bg-slate-800 hover:bg-cyan-900 border border-cyan-700 text-cyan-300 px-2 py-0.5 rounded text-[10px] font-bold">Verify on PayPal</button>`;
        }
      }
    ];

    function initGrid() {
      const gridDiv = document.getElementById("vaultGrid");
      gridApi = agGrid.createGrid(gridDiv, {
        columnDefs,
        rowData: [],
        pinnedBottomRowData: [],
        rowSelection: "single",
        animateRows: true,
        getRowId: params => params.data.order_id,
        onRowClicked: e => { if (!e.node.rowPinned) renderOrderInspector(e.data); }
      });
    }

    async function verifyOrderOnPayPal(orderId) {
      const modal = document.getElementById("paypalModal");
      const pre = document.getElementById("modalJson");
      document.getElementById("modalTitle").innerText = `Fetching GET https://api-m.sandbox.paypal.com/v2/checkout/orders/${orderId} ...`;
      pre.innerText = "Querying PayPal Sandbox servers...";
      modal.classList.remove("hidden");
      modal.classList.add("flex");

      const res = await fetch(`/api/paypal/order/${orderId}`);
      const data = await res.json();
      document.getElementById("modalTitle").innerText = `Live PayPal Server Response — Order ${orderId} (Paypal-Debug-Id: ${data.paypal_debug_id})`;
      pre.innerText = JSON.stringify(data, null, 2);
    }

    function closeModal() {
      const modal = document.getElementById("paypalModal");
      modal.classList.add("hidden");
      modal.classList.remove("flex");
    }

    function onQuickFilter() {
      gridApi.setGridOption("quickFilterText", document.getElementById("quickFilter").value);
    }

    function exportCsv() {
      gridApi.exportDataAsCsv({ fileName: "zerohold_evidence_vault.csv" });
    }

    function renderOrderInspector(order) {
      const panel = document.getElementById("dossierPanel");
      const dossier = latestState?.latest_dossier;
      const btn = document.getElementById("printableDossierBtn");
      if (dossier) {
        btn.classList.remove("hidden");
      } else {
        btn.classList.add("hidden");
      }

      panel.innerHTML = `
        <div class="bg-slate-950 border border-slate-800 p-3 rounded space-y-1.5">
          <div class="flex justify-between">
            <span class="font-bold text-cyan-300">Selected PayPal Order: ${order.order_id}</span>
            <span class="text-emerald-400 font-bold">$${order.amount_usd.toFixed(2)}</span>
          </div>
          <div class="grid grid-cols-2 gap-2 text-[11px] text-slate-300 pt-1">
            <div><span class="text-slate-500">Supplier Invoice:</span> <code>${order.supplier_invoice_id}</code> (${order.warehouse_bin})</div>
            <div><span class="text-slate-500">Visa CE 3.0 Prior Orders:</span> ${order.prior_undisputed_orders} undisputed captures</div>
            <div><span class="text-slate-500">Checkout IP / Device:</span> ${order.buyer_ip} / <code>${order.device_hash}</code></div>
            <div><span class="text-slate-500">GPS Delivery Scan:</span> ${order.gps_proof || 'Pending carrier sync'}</div>
          </div>
        </div>
        ${dossier ? renderDossierHtml(dossier) : '<div class="text-slate-500">Click "2. Run Autonomous Freeze Defuser" after a volume spike to collate the SKU-to-Supplier-Invoice Underwriting Dossier.</div>'}
      `;
    }

    function renderDossierHtml(d) {
      const tableRows = (d.collated_orders || []).map(item => `
        <tr class="border-b border-slate-800 text-[10px]">
          <td class="py-1 font-bold text-cyan-300">${item.paypal_order_id}</td>
          <td class="py-1">${item.sku} ($${item.amount_usd})</td>
          <td class="py-1 text-amber-300">${item.supplier_invoice_id} ($${item.wholesale_cost_usd} cost)</td>
          <td class="py-1 text-emerald-300">${item.carrier} #${item.tracking_number}</td>
        </tr>
      `).join('');

      return `
        <div class="bg-slate-950 border border-emerald-800/80 p-3 rounded space-y-2">
          <div class="flex justify-between items-center">
            <span class="font-bold text-emerald-400">${d.dossier_id} (${d.synced_captures} Spiked Orders Reconciled)</span>
            <span class="text-[10px] bg-emerald-900 text-emerald-200 px-2 py-0.5 rounded font-bold">Freeze Risk: ${d.freeze_risk_drop}</span>
          </div>
          <div class="text-[11px] text-slate-300">
            Verified Wholesale Inventory Basis: <strong class="text-emerald-300">$${(d.total_wholesale_inventory_verified_usd || 0).toLocaleString()} USD</strong> across ${d.synced_captures} distributor invoices.
          </div>
          <table class="w-full text-left border-t border-slate-800 mt-1">
            <thead><tr class="text-[10px] text-slate-500 border-b border-slate-800">
              <th class="py-1">PayPal Order</th><th class="py-1">SKU</th><th class="py-1">Wholesale PO</th><th class="py-1">Synced Waybill</th>
            </tr></thead>
            <tbody>${tableRows}</tbody>
          </table>
        </div>
      `;
    }

    function updateDashboard(data) {
      latestState = data;
      const m = data.metrics;

      document.getElementById("sdkBadge").innerHTML = m.apimatic_connected
        ? `<span class="text-emerald-400 font-bold">● APIMatic SDK v2.4.0 + Sandbox Live</span>`
        : `<span class="text-amber-400 font-bold">● Check .envrc Credentials</span>`;

      const fScore = document.getElementById("freezeScore");
      const fState = document.getElementById("freezeState");
      const fCard = document.getElementById("freezeCard");
      fScore.innerText = `${m.freeze_risk_score} / 100`;
      fState.innerText = m.freeze_state;

      if (m.freeze_risk_score >= 70) {
        fScore.className = "text-2xl font-bold text-rose-400 animate-pulse";
        fState.className = "text-[11px] font-bold text-rose-300";
        fCard.className = "border border-rose-700 bg-rose-950/30 p-4 rounded-lg space-y-1";
      } else {
        fScore.className = "text-2xl font-bold text-emerald-400";
        fState.className = "text-[11px] font-bold text-emerald-300";
        fCard.className = "border border-slate-800 bg-slate-900/80 p-4 rounded-lg space-y-1";
      }

      document.getElementById("gmvValue").innerText = `$${m.gmv_24h.toLocaleString('en-US', {minimumFractionDigits: 2})}`;
      document.getElementById("gmvSub").innerText = `${m.gmv_multiplier}x Baseline ($4,000) | Welford Z = +${m.z_gmv}σ`;

      document.getElementById("protectedValue").innerText = `${m.protected_pct}% ($${m.protected_gmv_usd.toLocaleString()})`;
      document.getElementById("untrackedSub").innerText = m.untracked_count > 0
        ? `${m.untracked_count} Untracked Captures ($${m.untracked_exposure_usd.toLocaleString()} Hold Exposure)`
        : `0 Untracked Captures — 100% Seller-Protected`;

      document.getElementById("disputeValue").innerText = `${m.dispute_ratio_pct}%`;

      gridApi.setGridOption("rowData", data.orders);
      gridApi.setGridOption("pinnedBottomRowData", [{
        order_id: `TOTAL (${m.total_orders} ORDERS)`,
        amount_usd: m.gmv_24h,
        item_name: `Protected: $${m.protected_gmv_usd.toLocaleString()} (${m.protected_pct}%)`,
        tracking_number: m.untracked_count > 0 ? `${m.untracked_count} Untracked` : "All Synced"
      }]);

      if (data.orders.length > 0) {
        renderOrderInspector(data.orders[0]);
      }

      const logEl = document.getElementById("auditLogPanel");
      logEl.innerHTML = (data.audit_logs || []).map(l => `
        <div class="border border-slate-800 bg-slate-950 p-2.5 rounded space-y-1">
          <div class="flex justify-between items-center">
            <span class="font-bold text-cyan-300">${l.sdk_component}</span>
            <span class="px-1.5 py-0.5 rounded text-[10px] font-bold ${l.http_status < 300 ? 'bg-emerald-950 text-emerald-300' : 'bg-amber-950 text-amber-300'}">
              HTTP ${l.http_status} (${l.latency_ms}ms)
            </span>
          </div>
          <div class="text-slate-300">${l.summary}</div>
          <div class="text-slate-500 text-[10px]"><code>${l.endpoint}</code></div>
        </div>
      `).join('');
    }

    async function runAction(url) {
      const sp = document.getElementById("statusSpinner");
      sp.classList.remove("hidden");
      try {
        const res = await fetch(url, { method: "POST" });
        const data = await res.json();
        updateDashboard(data);
      } finally {
        sp.classList.add("hidden");
      }
    }

    async function loadInitial() {
      initGrid();
      const sp = document.getElementById("statusSpinner");
      sp.classList.remove("hidden");
      const res = await fetch("/api/state");
      const data = await res.json();
      updateDashboard(data);
      sp.classList.add("hidden");
    }

    loadInitial();
  </script>
</body>
</html>""")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
