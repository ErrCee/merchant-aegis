import json
from typing import Any
from fastapi import Body, FastAPI
from fastapi.responses import HTMLResponse
import uvicorn

from db import get_conn, init_db, reset_demo_db
from sentinel import (
    compute_account_health,
    create_and_vault_live_sandbox_order,
    execute_merchant_attested_reconciliation,
    handle_paypal_dispute_webhook,
    reset_order_dispute_state,
    paypal_client,
    trigger_viral_flash_sale,
)

init_db(seed_initial=True)
app = FastAPI(title="ZeroHold // Merchant Treasury & Seller Protection Workbench")


@app.get("/api/state")
async def api_state() -> dict:
    return compute_account_health()


# Production-Ready Webhook & Reconciliation Routes
@app.post("/api/v1/fulfillment/reconcile")
async def api_reconcile_fulfillment(payload: dict[str, Any] = Body(...)) -> dict:
    """Production Human-in-the-Loop Merchant Attestation & Batch Waybill Reconciliation."""
    return execute_merchant_attested_reconciliation(payload)


@app.post("/webhooks/paypal/dispute-created")
async def webhook_paypal_dispute(payload: dict[str, Any] = Body(default={})) -> dict:
    """Production PayPal Webhook Receiver (`CUSTOMER.DISPUTE.CREATED`)."""
    reason = payload.get("reason", "UNAUTHORISED")
    order_id = payload.get("order_id")
    return handle_paypal_dispute_webhook(dispute_reason=reason, order_id=order_id)


# Backward-compatible test harness endpoints
@app.post("/api/simulate/flash-sale")
async def api_flash_sale() -> dict:
    return trigger_viral_flash_sale()


@app.post("/api/simulate/defuse-freeze")
async def api_defuse_freeze() -> dict:
    return execute_merchant_attested_reconciliation({})


@app.post("/api/simulate/friendly-fraud")
async def api_friendly_fraud(payload: dict[str, Any] = Body(default={})) -> dict:
    reason = payload.get("reason", "UNAUTHORISED")
    return handle_paypal_dispute_webhook(dispute_reason=reason)


@app.post("/api/simulate/live-sandbox-order")
async def api_live_sandbox() -> dict:
    return create_and_vault_live_sandbox_order()


@app.post("/api/orders/{order_id}/reset-dispute")
async def api_reset_single_dispute(order_id: str) -> dict:
    return reset_order_dispute_state(order_id)


@app.get("/api/paypal/order/{order_id}")
async def api_verify_order_on_paypal(order_id: str) -> dict:
    return paypal_client.fetch_live_order_from_paypal(order_id)


@app.get("/api/dossier/latest/report", response_class=HTMLResponse)
async def api_printable_dossier_report() -> HTMLResponse:
    conn = get_conn()
    row = conn.execute("SELECT * FROM legitimacy_dossiers ORDER BY created_at DESC LIMIT 1").fetchone()
    conn.close()
    if not row:
        return HTMLResponse("<h3>No Dossier Generated Yet. Reconcile untracked orders first.</h3>")

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
      <div class="text-xs font-mono uppercase tracking-widest text-slate-500">MERCHANT-ATTESTED RESOLUTION CENTER SUBMISSION</div>
      <h1 class="text-2xl font-bold mt-1">PayPal Pre-Freeze Account Legitimacy &amp; Fulfillment Dossier</h1>
      <p class="text-sm text-slate-600">Dossier ID: <strong>{d['dossier_id']}</strong> | Attested By: <strong>{d.get('attested_by', 'ops.lead@merchant.io')}</strong> | Hub: <strong>{d.get('warehouse_hub', '')}</strong></p>
    </div>
    <button onclick="window.print()" class="bg-slate-900 text-white px-4 py-2 rounded text-xs font-bold hover:bg-slate-700">
      Print / Export Resolution Center PDF
    </button>
  </div>

  <div class="grid grid-cols-3 gap-4 bg-slate-100 p-4 rounded border border-slate-300 text-sm">
    <div><span class="text-slate-500 block text-xs">Velocity Event &amp; Campaign</span><strong>{d['headline']} ({d.get('campaign_utm', '')})</strong></div>
    <div><span class="text-slate-500 block text-xs">Unbacked Exposure Mitigation</span><strong class="text-emerald-700">{d['freeze_risk_drop']}</strong></div>
    <div><span class="text-slate-500 block text-xs">Attested Wholesale Inventory Basis</span><strong>${d.get('total_wholesale_inventory_verified_usd', 0):,.2f} USD (100% In-Stock)</strong></div>
  </div>

  <div>
    <h2 class="text-sm font-bold uppercase tracking-wider mb-2">1. Order-by-Order Supplier Invoice &amp; Live PayPal Waybill Reconciliation</h2>
    <table class="w-full text-left border border-slate-300 text-sm">
      <thead class="bg-slate-200 text-xs uppercase">
        <tr>
          <th class="p-2">PayPal Order ID</th>
          <th class="p-2">Item &amp; SKU</th>
          <th class="p-2">Capture</th>
          <th class="p-2">Attested Distributor Invoice &amp; Bin</th>
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
  <title>ZeroHold // Merchant Treasury &amp; Seller Protection Workbench</title>
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
      --ag-row-height: 36px;
      --ag-cell-horizontal-padding: 10px;
    }
    .ag-theme-quartz-dark .ag-cell-wrap-text {
      line-height: 1.35 !important;
      padding-top: 6px !important;
      padding-bottom: 6px !important;
      display: flex;
      align-items: center;
    }
  </style>
</head>
<body class="p-5">
  <div class="max-w-[1460px] mx-auto space-y-4">

    <!-- Top Production Header -->
    <div class="flex flex-wrap justify-between items-center border-b border-slate-800 pb-3 gap-3">
      <div>
        <div class="flex items-center gap-3">
          <span class="text-xl font-bold text-emerald-400 tracking-tight">ZEROHOLD</span>
          <span class="text-xs bg-slate-900 border border-slate-700 text-slate-200 px-2.5 py-0.5 rounded font-semibold">
            Merchant Treasury Compliance &amp; Visa CE 3.0 Auto-Defense Workbench
          </span>
        </div>
        <p class="text-xs text-slate-400 mt-1">
          Production Integration: <strong class="text-cyan-300">APIMatic PayPal Server SDK (v2.4.0)</strong> &bull; <strong class="text-amber-300">AG Grid v31</strong> &bull; <strong class="text-emerald-300">Relational SQLite WAL Evidence Vault</strong>
        </p>
      </div>
      <div class="flex items-center gap-2">
        <span id="sdkBadge" class="text-xs px-3 py-1.5 rounded border border-slate-700 bg-slate-900 text-cyan-300">
          Checking APIMatic SDK...
        </span>
        <button onclick="runAction('/api/reset')" class="text-xs bg-slate-800 hover:bg-slate-700 border border-slate-600 px-3 py-1.5 rounded text-slate-300">
          Reset Sandbox Environment
        </button>
      </div>
    </div>

    <!-- 4 Live Telemetry Gauges (Framed as Merchant Compliance & Unbacked Exposure) -->
    <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
      <div id="freezeCard" class="border border-slate-800 bg-slate-900/80 p-4 rounded-lg space-y-1">
        <div class="text-[11px] text-slate-400 uppercase">Unbacked Capture &amp; Reserve Exposure</div>
        <div id="freezeScore" class="text-2xl font-bold text-emerald-400">-- / 100</div>
        <div id="freezeState" class="text-[11px] font-bold text-emerald-300">--</div>
      </div>

      <div class="border border-slate-800 bg-slate-900/80 p-4 rounded-lg space-y-1">
        <div class="text-[11px] text-slate-400 uppercase">24h GMV Velocity (Welford Z-Score)</div>
        <div id="gmvValue" class="text-2xl font-bold text-cyan-400">$0.00</div>
        <div id="gmvSub" class="text-[11px] text-slate-400">Baseline: $4,000/day</div>
      </div>

      <div class="border border-slate-800 bg-slate-900/80 p-4 rounded-lg space-y-1">
        <div class="text-[11px] text-slate-400 uppercase">Seller-Protected &amp; PO-Backed Volume</div>
        <div id="protectedValue" class="text-2xl font-bold text-emerald-400">100%</div>
        <div id="untrackedSub" class="text-[11px] text-slate-400">0 Untracked Captures</div>
      </div>

      <div class="border border-slate-800 bg-slate-900/80 p-4 rounded-lg space-y-1">
        <div class="text-[11px] text-slate-400 uppercase">Dispute Ratio vs. 1.50% VAMP Cap</div>
        <div id="disputeValue" class="text-2xl font-bold text-sky-400">0.86%</div>
        <div class="text-[11px] text-slate-400">30d Rolling Window (350 Captures)</div>
      </div>
    </div>

    <!-- Primary Merchant Operations Bar (Driven Directly by AG Grid Inline Editing) -->
    <div class="border border-slate-800 bg-slate-900/70 p-3.5 rounded-lg flex flex-wrap items-center justify-between gap-3">
      <div class="flex flex-wrap items-center gap-2">
        <span class="text-[11px] font-bold uppercase text-slate-400 mr-1">3PL &amp; AG Grid Actions:</span>
        <button onclick="pullWarehouseManifestIntoGrid()"
          class="text-xs font-bold bg-cyan-600 hover:bg-cyan-500 text-slate-950 px-3 py-2 rounded shadow"
          title="Simulates pulling printed FedEx/DHL/UPS labels and wholesale POs from ShipStation/Delhivery WMS into AG Grid cells">
          1. Pull 3PL Warehouse Manifest into AG Grid
        </button>
        <button id="reconcileModalBtn" onclick="openReconciliationModal()"
          class="text-xs font-bold bg-emerald-500 hover:bg-emerald-400 text-slate-950 px-3.5 py-2 rounded shadow flex items-center gap-1.5">
          <span>2. Attest &amp; Sync AG Grid Waybills to PayPal</span>
          <span id="untrackedBadge" class="bg-slate-950 text-emerald-300 px-1.5 py-0.5 rounded text-[10px]">0 Pending</span>
        </button>
        <button onclick="runAction('/api/simulate/live-sandbox-order')"
          class="text-xs font-bold bg-slate-800 hover:bg-slate-700 border border-slate-600 text-slate-200 px-3 py-2 rounded">
          + Ingest 1 Sandbox Order
        </button>
      </div>

      <!-- Webhook & Traffic Test Harness for Hackathon Judges -->
      <div class="flex flex-wrap items-center gap-2 border-l border-slate-800 pl-3">
        <span class="text-[10px] uppercase tracking-wider text-slate-400">Webhook Test Harness:</span>
        <button onclick="runAction('/api/simulate/flash-sale')"
          class="text-xs bg-amber-950/90 hover:bg-amber-900 border border-amber-700 text-amber-200 px-2.5 py-1.5 rounded">
          Ingest 5-Order Flash Sale ($17k Unbacked)
        </button>
        <button onclick="fireDisputeWebhook('UNAUTHORISED')"
          class="text-xs bg-rose-950/90 hover:bg-rose-900 border border-rose-700 text-rose-200 px-2.5 py-1.5 rounded">
          Webhook: UNAUTHORISED (Visa CE 3.0 SQL Match)
        </button>
        <button onclick="fireDisputeWebhook('MERCHANDISE_OR_SERVICE_NOT_RECEIVED')"
          class="text-xs bg-purple-950/90 hover:bg-purple-900 border border-purple-700 text-purple-200 px-2.5 py-1.5 rounded">
          Webhook: ITEM_NOT_RECEIVED (GPS POD Match)
        </button>
      </div>
    </div>

    <!-- AG Grid Order Evidence Vault -->
    <div class="space-y-2">
      <div class="flex flex-wrap justify-between items-center gap-2">
        <div class="flex items-center gap-3">
          <h2 class="text-xs font-bold uppercase tracking-wider text-slate-300">
            AG Grid Interactive Evidence Vault <span class="text-cyan-400 font-normal normal-case">(Click any Carrier, Waybill, or Supplier PO cell to edit inline &bull; Use Floating Filters below headers)</span>
          </h2>
          <span id="statusSpinner" class="text-xs text-amber-400 font-bold hidden animate-pulse">
            Executing Live HTTPS Calls to api-m.sandbox.paypal.com...
          </span>
        </div>
        <div class="flex items-center gap-2">
          <input id="quickFilter" oninput="onQuickFilter()" type="text" placeholder="Filter AG Grid (Order ID, SKU, PO, Hash)..."
            class="text-xs bg-slate-950 border border-slate-700 rounded px-3 py-1 text-slate-200 w-64" />
          <button onclick="exportCsv()" class="text-xs bg-slate-800 hover:bg-slate-700 border border-slate-700 px-3 py-1 rounded text-cyan-300">
            Export Vault CSV
          </button>
        </div>
      </div>
      <div id="vaultGrid" class="ag-theme-quartz-dark w-full h-[390px] rounded-lg border border-slate-800"></div>
    </div>

    <!-- Bottom Dual Inspector -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div class="border border-slate-800 bg-slate-900/70 p-4 rounded-lg space-y-3">
        <div class="flex justify-between items-center border-b border-slate-800 pb-2">
          <span class="text-xs font-bold text-cyan-400 uppercase">
            Relational Visa CE 3.0 Match Graph &amp; Attested Underwriting Dossier
          </span>
          <a id="printableDossierBtn" href="/api/dossier/latest/report" target="_blank"
            class="hidden text-[11px] bg-emerald-600 hover:bg-emerald-500 text-slate-950 font-bold px-2.5 py-1 rounded">
            Open Printable Resolution Center Packet &nearr;
          </a>
        </div>
        <div id="dossierPanel" class="text-xs text-slate-300 space-y-3 max-h-[320px] overflow-y-auto pr-1"></div>
      </div>

      <div class="border border-slate-800 bg-slate-900/70 p-4 rounded-lg space-y-3">
        <div class="text-xs font-bold text-emerald-400 uppercase border-b border-slate-800 pb-2">
          Live Outbound APIMatic SDK &amp; PayPal Sandbox Stream (With Paypal-Debug-Id)
        </div>
        <div id="auditLogPanel" class="space-y-2 max-h-[320px] overflow-y-auto pr-1 text-[11px]"></div>
      </div>
    </div>

  </div>

  <!-- MODAL 1: Human-in-the-Loop Merchant Fulfillment & Supplier Invoice Attestation Modal -->
  <div id="reconcileModal" class="fixed inset-0 bg-black/85 hidden items-center justify-center p-4 z-50">
    <div class="bg-slate-900 border border-emerald-600 rounded-lg max-w-5xl w-full p-5 space-y-4 shadow-2xl">
      <div class="flex justify-between items-start border-b border-slate-800 pb-3">
        <div>
          <span class="text-xs uppercase font-bold text-emerald-400">Human-in-the-Loop Underwriting Gate</span>
          <h3 class="text-base font-bold text-slate-100 mt-0.5">
            Confirm Carrier Waybills &amp; Attest Wholesale Supplier Invoices Before Syncing to PayPal
          </h3>
          <p class="text-xs text-slate-400">
            Review or edit the warehouse tracking numbers and distributor purchase order IDs below. Submitting will call <code>PATCH /v2/checkout/orders/{id}</code> and <code>POST /v1/shipping/trackers-batch</code> on PayPal Sandbox.
          </p>
        </div>
        <button onclick="closeReconcileModal()" class="text-xs bg-slate-800 hover:bg-slate-700 px-3 py-1 rounded text-slate-300">Cancel</button>
      </div>

      <!-- Global Attestation Metadata Inputs -->
      <div class="grid grid-cols-1 md:grid-cols-3 gap-3 bg-slate-950 p-3 rounded border border-slate-800 text-xs">
        <div>
          <label class="block text-slate-400 mb-1">3PL Fulfillment Hub / Manifest</label>
          <input id="inpWarehouseHub" type="text" value="Bengaluru Central 3PL Hub (MANIFEST-BLR-99410)"
            class="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 text-slate-100" />
        </div>
        <div>
          <label class="block text-slate-400 mb-1">Traffic Surge Attribution / Campaign Ref</label>
          <input id="inpCampaignUtm" type="text" value="UTM-CREATOR-FEST-2026 (YouTube Sponsor Drop)"
            class="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 text-slate-100" />
        </div>
        <div>
          <label class="block text-slate-400 mb-1">Attesting Merchant Officer Email</label>
          <input id="inpAttestedBy" type="text" value="sayan.mandal@zerohold-ops.in"
            class="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 text-slate-100" />
        </div>
      </div>

      <!-- Editable Per-Order Waybill & Supplier PO Table -->
      <div class="max-h-[260px] overflow-y-auto border border-slate-800 rounded">
        <table class="w-full text-left text-xs">
          <thead class="bg-slate-800 text-slate-300 uppercase text-[10px]">
            <tr>
              <th class="p-2">PayPal Order ID</th>
              <th class="p-2">SKU &amp; Amount</th>
              <th class="p-2">Carrier</th>
              <th class="p-2">Carrier Tracking Waybill (Editable)</th>
              <th class="p-2">Wholesale Supplier Invoice ID (Editable)</th>
            </tr>
          </thead>
          <tbody id="reconcileTableBody" class="divide-y divide-slate-800 bg-slate-950"></tbody>
        </table>
      </div>

      <div class="flex flex-wrap justify-between items-center pt-2 gap-3">
        <label class="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
          <input id="chkAttest" type="checkbox" checked class="rounded border-slate-600 text-emerald-500" />
          <span>I attest that physical stock for these SKUs is held in warehouse bins and dispatched via the listed waybills.</span>
        </label>
        <button id="btnSubmitAttestation" onclick="submitMerchantAttestation()"
          class="bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold text-xs px-5 py-2.5 rounded shadow">
          Sync Waybills to PayPal Sandbox &amp; Generate Resolution Center Packet
        </button>
      </div>
    </div>
  </div>

  <!-- MODAL 2: Live PayPal Sandbox Server Verification Modal -->
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
    let selectedOrderId = null;

    const columnDefs = [
      { field: "order_id", headerName: "PayPal Order ID", width: 170, pinned: "left",
        filter: "agTextColumnFilter", floatingFilter: true,
        checkboxSelection: p => !p.node.rowPinned,
        headerCheckboxSelection: true,
        cellClass: "font-bold text-cyan-300" },
      { field: "amount_usd", headerName: "Amount", width: 110, enableCellChangeFlash: true,
        filter: "agNumberColumnFilter", floatingFilter: true,
        valueFormatter: p => p.value !== undefined ? `$${Number(p.value).toFixed(2)}` : "",
        cellClass: "font-bold text-slate-100" },
      { field: "item_name", headerName: "Product & SKU", flex: 1, minWidth: 185,
        filter: "agTextColumnFilter", floatingFilter: true,
        cellRenderer: p => p.node.rowPinned ? `<strong class="text-amber-300">${p.value}</strong>` : `<span>${p.value} <code class="text-[10px] text-slate-400">[${p.data.sku}]</code></span>` },
      { field: "supplier_invoice_id", headerName: "Wholesale PO (Editable)", width: 165,
        editable: p => !p.node.rowPinned,
        cellEditor: "agTextCellEditor",
        enableCellChangeFlash: true,
        filter: "agTextColumnFilter", floatingFilter: true,
        cellRenderer: p => {
          if (p.node.rowPinned) return "";
          return `<span class="text-amber-300 border-b border-dashed border-amber-700/70 pb-0.5" title="Click to edit Wholesale Supplier Invoice ID inline">${p.value || 'Click to enter PO'} &crarr;</span>`;
        }
      },
      { field: "carrier", headerName: "Carrier (Editable)", width: 130,
        editable: p => !p.node.rowPinned,
        cellEditor: "agSelectCellEditor",
        cellEditorParams: { values: ["FEDEX", "DHL", "UPS", "BLUEDART"] },
        enableCellChangeFlash: true,
        cellRenderer: p => {
          if (p.node.rowPinned) return "";
          return p.value
            ? `<span class="text-cyan-300 font-bold border-b border-dashed border-cyan-700/70">${p.value} &darr;</span>`
            : `<span class="text-slate-400 border-b border-dashed border-slate-600">${p.data.suggested_carrier || 'FEDEX'} &darr;</span>`;
        }
      },
      { field: "tracking_number", headerName: "Waybill (Inline Editable)", width: 185,
        editable: p => !p.node.rowPinned,
        cellEditor: "agTextCellEditor",
        enableCellChangeFlash: true,
        filter: "agTextColumnFilter", floatingFilter: true,
        cellRenderer: p => {
          if (p.node.rowPinned) return `<strong class="text-cyan-300">${p.value || ''}</strong>`;
          if (p.value && p.data._staged_only) {
            return `<span class="text-amber-300 font-bold border-b border-dashed border-amber-500" title="Staged from 3PL WMS — Click '2. Attest & Sync' to push to PayPal">${p.value} (STAGED) &crarr;</span>`;
          }
          return p.value
            ? `<span class="text-emerald-300 font-bold border-b border-dashed border-emerald-700/60" title="Click to edit waybill inline">${p.value} &crarr;</span>`
            : `<span class="text-amber-400 font-semibold animate-pulse border-b border-dashed border-amber-600" title="Click to type waybill or click '1. Pull 3PL Warehouse Manifest'">+ Click or Pull WMS</span>`;
        }
      },
      { field: "prior_undisputed_orders", headerName: "Visa CE 3.0 SQL", width: 165, enableCellChangeFlash: true,
        cellRenderer: p => {
          if (p.node.rowPinned) return "";
          const cnt = p.value || 0;
          return cnt >= 2
            ? `<span class="text-emerald-300 font-bold text-[11px]">&check; ${cnt} Settled (CE 3.0 OK)</span>`
            : `<span class="text-amber-400 font-bold text-[11px]">&cross; ${cnt} Settled (Min 2)</span>`;
        }
      },
      { field: "seller_protection", headerName: "Seller Protection", width: 150, enableCellChangeFlash: true,
        cellRenderer: p => {
          if (p.node.rowPinned) return "";
          return p.value === "ELIGIBLE_ACTIVE"
            ? `<span class="text-emerald-400 text-[11px] font-semibold tracking-tight">&bull; Eligible &middot; Active</span>`
            : `<span class="text-amber-400 text-[11px] font-semibold tracking-tight">&bull; Unbacked Exposure</span>`;
        }
      },
      { field: "dispute_status", headerName: "Dispute Auto-Defense", width: 220, enableCellChangeFlash: true,
        cellRenderer: p => {
          if (p.node.rowPinned) return "";
          const resetBtn = `<button onclick="event.stopPropagation(); resetSingleDispute('${p.data.order_id}')" title="Clear dispute to test another webhook" class="ml-1.5 text-slate-400 hover:text-slate-100 bg-slate-800 px-1 rounded text-[10px]">&orarr;</button>`;
          if (p.value === "AUTO_DEFENDED_PROTECTED") {
            const tag = p.data.dispute_reason === 'UNAUTHORISED' ? 'CE 3.0 SQL' : 'GPS POD';
            return `<div class="flex items-center justify-between w-full"><span class="text-emerald-400 text-[11px] font-bold">&check; Auto-Defended (${tag})</span>${resetBtn}</div>`;
          }
          if (p.value && p.value.startsWith("ESCALATED")) {
            const lbl = p.value === "ESCALATED_CE3_EXHAUSTED" ? "Escalated (CE3 < 2 Prior)" : "Escalated (No Waybill)";
            return `<div class="flex items-center justify-between w-full"><span class="text-rose-400 text-[11px] font-bold animate-pulse">&triangle; ${lbl}</span>${resetBtn}</div>`;
          }
          return `<div class="flex items-center gap-1.5 h-full">
            <span class="text-slate-500 text-[11px]">None</span>
            <button onclick="event.stopPropagation(); fireDisputeWebhook('UNAUTHORISED', '${p.data.order_id}')" title="Fire UNAUTHORISED (Stolen Card/CE 3.0) Webhook" class="bg-rose-950/80 hover:bg-rose-800 border border-rose-700 text-rose-200 px-1.5 py-0.5 rounded text-[9px] font-bold">CE3</button>
            <button onclick="event.stopPropagation(); fireDisputeWebhook('MERCHANDISE_OR_SERVICE_NOT_RECEIVED', '${p.data.order_id}')" title="Fire ITEM_NOT_RECEIVED (Carrier POD) Webhook" class="bg-purple-950/80 hover:bg-purple-800 border border-purple-700 text-purple-200 px-1.5 py-0.5 rounded text-[9px] font-bold">INR</button>
          </div>`;
        }
      },
      { headerName: "Live PayPal Check", width: 135, pinned: "right",
        cellRenderer: p => {
          if (p.node.rowPinned) return "";
          return `<button onclick="verifyOrderOnPayPal('${p.data.order_id}')" class="bg-slate-800 hover:bg-cyan-900 border border-cyan-700 text-cyan-300 px-2 py-0.5 rounded text-[10px] font-bold">Verify on PayPal</button>`;
        }
      }
    ];

    function initGrid() {
      const gridDiv = document.getElementById("vaultGrid");
      gridApi = agGrid.createGrid(gridDiv, {
        defaultColDef: {
          wrapText: true,
          autoHeight: true,
          resizable: true,
          sortable: true,
          tooltipValueGetter: p => {
            if (!p.data) return "";
            return `Order: ${p.data.order_id} | Buyer: ${p.data.buyer_email} | Product: ${p.data.item_name} [${p.data.sku}] | Waybill: ${p.data.carrier || 'NONE'} #${p.data.tracking_number || 'UNTRACKED'} | PO: ${p.data.supplier_invoice_id} (Click Carrier, Waybill, or PO cells to edit inline)`;
          }
        },
        singleClickEdit: true,
        stopEditingWhenCellsLoseFocus: true,
        tooltipShowDelay: 150,
        columnDefs,
        rowData: [],
        pinnedBottomRowData: [],
        rowSelection: "multiple",
        suppressRowClickSelection: true,
        animateRows: true,
        getRowId: params => params.data.order_id,
        onRowClicked: e => { if (!e.node.rowPinned) { selectedOrderId = e.data.order_id; renderOrderInspector(e.data); } },
        onCellValueChanged: e => {
          e.data._staged_only = true;
          gridApi.refreshCells({ rowNodes: [e.node], force: true });
          renderOrderInspector(e.data);
        }
      });
    }

    function pullWarehouseManifestIntoGrid() {
      if (!gridApi) return;
      let stagedCount = 0;
      gridApi.forEachNode(node => {
        if (!node.rowPinned && (!node.data.tracking_number || node.data._staged_only)) {
          node.setDataValue("carrier", node.data.carrier || node.data.suggested_carrier || "FEDEX");
          node.setDataValue("tracking_number", node.data.suggested_tracking);
          node.data._staged_only = true;
          node.setSelected(true);
          stagedCount++;
        }
      });
      gridApi.refreshCells({ force: true });
    }

    function openReconciliationModal() {
      if (!gridApi) return;
      const allGridOrders = [];
      gridApi.forEachNode(n => { if (!n.rowPinned) allGridOrders.push(n.data); });
      const pending = allGridOrders.filter(o => !o.tracking_number || o._staged_only || o.seller_protection !== "ELIGIBLE_ACTIVE");
      const targetList = pending.length > 0 ? pending : allGridOrders;

      const tbody = document.getElementById("reconcileTableBody");
      tbody.innerHTML = targetList.map((o, idx) => `
        <tr data-order-id="${o.order_id}">
          <td class="p-2 font-bold text-cyan-300">${o.order_id}</td>
          <td class="p-2">${o.item_name} <code class="text-slate-400">[${o.sku}]</code> — <strong>$${o.amount_usd.toFixed(2)}</strong></td>
          <td class="p-2">
            <select class="rec-carrier bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-100">
              <option value="FEDEX" ${(o.carrier || o.suggested_carrier) === 'FEDEX' ? 'selected' : ''}>FEDEX</option>
              <option value="DHL" ${(o.carrier || o.suggested_carrier) === 'DHL' ? 'selected' : ''}>DHL</option>
              <option value="UPS" ${(o.carrier || o.suggested_carrier) === 'UPS' ? 'selected' : ''}>UPS</option>
            </select>
          </td>
          <td class="p-2">
            <input type="text" class="rec-tracking w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-emerald-300 font-bold"
              value="${o.tracking_number || o.suggested_tracking}" />
          </td>
          <td class="p-2">
            <input type="text" class="rec-po w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-amber-300"
              value="${o.supplier_invoice_id}" />
          </td>
        </tr>
      `).join('');

      const modal = document.getElementById("reconcileModal");
      modal.classList.remove("hidden");
      modal.classList.add("flex");
    }

    function closeReconcileModal() {
      const modal = document.getElementById("reconcileModal");
      modal.classList.add("hidden");
      modal.classList.remove("flex");
    }

    async function submitMerchantAttestation() {
      if (!document.getElementById("chkAttest").checked) {
        alert("Please check the Merchant Inventory Attestation box before syncing to PayPal.");
        return;
      }
      const rows = Array.from(document.querySelectorAll("#reconcileTableBody tr"));
      const items = rows.map(r => ({
        order_id: r.getAttribute("data-order-id"),
        carrier: r.querySelector(".rec-carrier").value,
        tracking_number: r.querySelector(".rec-tracking").value,
        supplier_invoice_id: r.querySelector(".rec-po").value,
      }));

      const payload = {
        warehouse_hub: document.getElementById("inpWarehouseHub").value,
        campaign_utm: document.getElementById("inpCampaignUtm").value,
        attested_by: document.getElementById("inpAttestedBy").value,
        items,
      };

      closeReconcileModal();
      const sp = document.getElementById("statusSpinner");
      sp.classList.remove("hidden");
      try {
        const res = await fetch("/api/v1/fulfillment/reconcile", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await res.json();
        updateDashboard(data);
      } finally {
        sp.classList.add("hidden");
      }
    }

    async function resetSingleDispute(orderId) {
      const res = await fetch(`/api/orders/${orderId}/reset-dispute`, { method: "POST" });
      const data = await res.json();
      updateDashboard(data);
    }

    async function fireDisputeWebhook(reason, explicitOrderId = null) {
      const targetId = explicitOrderId || selectedOrderId || (latestState?.orders?.[0]?.order_id ?? null);
      selectedOrderId = targetId;
      const sp = document.getElementById("statusSpinner");
      sp.classList.remove("hidden");
      try {
        const res = await fetch("/webhooks/paypal/dispute-created", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ reason, order_id: targetId }),
        });
        const data = await res.json();
        updateDashboard(data);
      } finally {
        sp.classList.add("hidden");
      }
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

      const ce3Rows = (order.ce3_matches || []).map(m => m.was_disputed ? `
        <div class="flex justify-between text-[10px] bg-rose-950/40 px-2 py-1 rounded border border-rose-900/80">
          <span class="text-rose-300 font-bold">Capture ${m.hist_capture_id} (${m.sku})</span>
          <span class="text-slate-400">${m.settled_days_ago}d ago &bull; $${m.amount_usd}</span>
          <span class="text-rose-400 font-bold">&cross; EXCLUDED (Previously Disputed)</span>
        </div>
      ` : `
        <div class="flex justify-between text-[10px] bg-slate-900 px-2 py-1 rounded border border-slate-800">
          <span class="text-cyan-300 font-bold">Capture ${m.hist_capture_id} (${m.sku})</span>
          <span class="text-slate-400">${m.settled_days_ago}d ago &bull; $${m.amount_usd}</span>
          <span class="text-emerald-400 font-bold">&check; Matched: ${m.matched_identifiers.join(', ')}</span>
        </div>
      `).join('');

      panel.innerHTML = `
        <div class="bg-slate-950 border border-slate-800 p-3 rounded space-y-2">
          <div class="flex justify-between items-center">
            <span class="font-bold text-cyan-300">Order Forensic Vault: ${order.order_id}</span>
            <span class="text-[10px] bg-slate-900 border border-slate-700 px-2 py-0.5 rounded text-slate-300">
              SHA-256: <code>${order.evidence_sha256}</code>
            </span>
          </div>
          <div class="grid grid-cols-2 gap-2 text-[11px] text-slate-300">
            <div><span class="text-slate-500">Checkout IP / Device:</span> ${order.buyer_ip} / <code>${order.device_hash}</code></div>
            <div><span class="text-slate-500">Shipping Zip / PO:</span> ${order.shipping_zip} / <code>${order.supplier_invoice_id}</code></div>
            <div><span class="text-slate-500">Waybill:</span> ${order.carrier || 'UNASSIGNED'} #${order.tracking_number || 'PENDING'}</div>
            <div><span class="text-slate-500">Day-4 GPS Scan:</span> ${order.gps_proof || 'Awaiting carrier dispatch'}</div>
          </div>
          <div class="space-y-1 pt-1 border-t border-slate-800">
            <div class="text-[10px] uppercase font-bold text-emerald-400">
              Relational Visa CE 3.0 Historical Match Ledger (120–365 Day Window):
            </div>
            ${ce3Rows || '<div class="text-[11px] text-slate-500">Less than 2 historical orders in 120-365d window (Protected via Carrier GPS POD).</div>'}
          </div>
          ${order.dispute_id ? `
            <div class="bg-emerald-950/70 border border-emerald-700 p-2 rounded text-[11px] text-emerald-200">
              <strong>Webhook ${order.dispute_id} (${order.dispute_reason}):</strong> Auto-defended via <code>${order.dispute_reason === 'UNAUTHORISED' ? 'Visa CE 3.0 Historical Capture Intersection' : 'Archived Day-4 Carrier GPS Proof of Delivery'}</code>.
            </div>
          ` : ''}
        </div>
        ${dossier ? renderDossierHtml(dossier) : '<div class="text-slate-400 text-[11px]">Click <strong>"Reconcile Fulfillment &amp; Attest Supplier Invoices"</strong> above to review waybills, sign the inventory attestation, and compile the Resolution Center packet.</div>'}
      `;
    }

    function renderDossierHtml(d) {
      const tableRows = (d.collated_orders || []).map(item => `
        <tr class="border-b border-slate-800 text-[10px]">
          <td class="py-1 font-bold text-cyan-300">${item.paypal_order_id}</td>
          <td class="py-1">${item.sku} ($${item.amount_usd})</td>
          <td class="py-1 text-amber-300">${item.supplier_invoice_id}</td>
          <td class="py-1 text-emerald-300">${item.carrier} #${item.tracking_number}</td>
        </tr>
      `).join('');

      return `
        <div class="bg-slate-950 border border-emerald-800/80 p-3 rounded space-y-1.5">
          <div class="flex justify-between items-center">
            <span class="font-bold text-emerald-400">${d.dossier_id} (Attested by ${d.attested_by || 'Merchant Ops'})</span>
            <span class="text-[10px] bg-emerald-900 text-emerald-200 px-2 py-0.5 rounded font-bold">${d.freeze_risk_drop}</span>
          </div>
          <div class="text-[11px] text-slate-300">
            Hub: <strong>${d.warehouse_hub || 'BLR-01'}</strong> &bull; Wholesale Basis: <strong class="text-emerald-300">$${(d.total_wholesale_inventory_verified_usd || 0).toLocaleString()} USD</strong>
          </div>
          <table class="w-full text-left border-t border-slate-800 mt-1">
            <thead><tr class="text-[10px] text-slate-500 border-b border-slate-800">
              <th class="py-1">PayPal Order</th><th class="py-1">SKU</th><th class="py-1">Attested PO</th><th class="py-1">Synced Waybill</th>
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

      document.getElementById("untrackedBadge").innerText = `${m.untracked_count} Pending`;
      const recBtn = document.getElementById("reconcileModalBtn");
      if (m.untracked_count > 0) {
        recBtn.className = "text-xs font-bold bg-amber-500 hover:bg-amber-400 text-slate-950 px-4 py-2 rounded shadow flex items-center gap-1.5 animate-pulse";
      } else {
        recBtn.className = "text-xs font-bold bg-emerald-500 hover:bg-emerald-400 text-slate-950 px-4 py-2 rounded shadow flex items-center gap-1.5";
      }

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
        ? `${m.untracked_count} Unbacked Captures ($${m.untracked_exposure_usd.toLocaleString()} at Hold Risk)`
        : `0 Unbacked Captures — 100% Seller-Protected`;

      document.getElementById("disputeValue").innerText = `${m.dispute_ratio_pct}%`;

      gridApi.setGridOption("rowData", data.orders);
      gridApi.setGridOption("pinnedBottomRowData", [{
        order_id: `TOTAL (${m.total_orders} ORDERS)`,
        amount_usd: m.gmv_24h,
        item_name: `Protected: $${m.protected_gmv_usd.toLocaleString()} (${m.protected_pct}%)`,
        tracking_number: m.untracked_count > 0 ? `${m.untracked_count} Awaiting Attestation` : "All Attested"
      }]);

      if (data.orders.length > 0) {
        const current = data.orders.find(o => o.order_id === selectedOrderId) || data.orders[0];
        selectedOrderId = current.order_id;
        renderOrderInspector(current);
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
