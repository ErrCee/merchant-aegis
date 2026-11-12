# ZeroHold (`merchant-aegis`): Post-Capture Merchant Treasury, Relational Visa CE 3.0 Vault & Pre-Freeze Workbench

**Hackathon:** PayPal AI Hackathon  
**Sponsor Tracks Targeted:** Best Use of **APIMatic** (`paypal-server-sdk==2.4.0` + PayPal Context Plugin) · Best Use of **AG Grid** (`v31.3.2`)  
**Tech Stack:** Python (`FastAPI`), APIMatic PayPal Python Server SDK (`v2.4.0`), PayPal Sandbox REST APIs (`Orders v2`, `Customer Disputes v1`, `Transaction Search v1`), SQLite (`WAL` mode), AG Grid (`ag-theme-quartz-dark`)

---

## 1. Executive Summary & The Post-Capture Merchant Problem

Payment platforms are heavily weighted toward buyer protection and penalize honest merchants after payment capture. High-growth sellers on PayPal get squeezed from two sides:

### 1.1 First-Party Friendly Fraud & The 180-Day vs. 90-Day Log Gap
According to the *LexisNexis True Cost of Fraud Study* and *Chargebacks911* industry benchmarks, **61% to 71% of all e-commerce disputes are first-party "friendly fraud"**, where a legitimate buyer receives their order and later files a claim for `MERCHANDISE_OR_SERVICE_NOT_RECEIVED` (`INR`) or `UNAUTHORISED`. Every $1.00 of friendly fraud costs the seller **$4.61** after dispute fees ($15 to $20), administrative overhead, and lost stock. Merchants leave **43% of claims uncontested** and lose **78% of manually contested disputes** because of two operational gaps:
* **Courier Log Purge vs. Dispute Window Mismatch:** PayPal gives buyers **180 days** to file a dispute, while couriers (FedEx, UPS, USPS, DHL) purge public web-queryable tracking histories and GPS Proof of Delivery (POD) scans after **90 to 120 days** to recycle tracking number pools and sell extended archive add-ons. If a buyer opens an `INR` claim on Day 135, querying the courier API returns `404 Not Found` unless the merchant archived the GPS delivery scan on Day 4 when the package arrived.
* **Visa Compelling Evidence 3.0 (CE 3.0) Cross-Silo Fragmentation:** Under Visa CE 3.0 (Reason Code 10.4), automatically defeating an `UNAUTHORISED` claim requires proving that the same buyer settled **at least 2 prior undisputed PayPal transactions aged 120 to 365 days ago**, matching at least **2 of 4 core identifiers** (`User Account/Email`, `IP Address`, `Device Fingerprint`, `Shipping Address`), where **at least one match MUST be `IP Address` or `Device Fingerprint`**. Because storefront session logs, PayPal capture histories, and courier PODs live in three separate silos, sellers rarely assemble this proof within PayPal's 10-day response SLA.

### 1.2 The 21-Day Volume-Spike Reserve Freeze & 3PL Sync Lag
According to *Pitney Bowes* and *ShipBob* fulfillment benchmarks, **82% to 91% of warehouse shipping labels are printed within 1 to 4 hours of checkout** in 3PL Warehouse Management Systems (ShipStation, Delhivery, EasyPost), but **over 64% of mid-market merchants only sync tracking numbers back to the payment processor on a 24-to-48-hour nightly batch job**. When a store runs a successful product launch or creator drop and daily GMV jumps **4.6x from $4,000/day to $18,450/day**, PayPal's underwriting model only sees the payment rail: an extreme velocity spike ($Z > 3.0\sigma$) paired with `$17,010` in unshipped captures. Fearing a "bust-out scam", the automated risk system locks the seller's cash in a **21-day rolling reserve** right when they need working capital to pay suppliers.

---

## 2. Dual-Engine System Architecture

**ZeroHold (`merchant-aegis`)** operates strictly **post-capture** as a deployable merchant operations workbench combining autonomous webhook defense with human-in-the-loop 3PL waybill and supplier invoice attestation.

### 2.1 High-Level Topology

```mermaid
flowchart TD
    classDef paypal fill:#003087,stroke:#38bdf8,stroke-width:2px,color:#f8fafc
    classDef apimatic fill:#0f172a,stroke:#818cf8,stroke-width:2px,color:#e2e8f0
    classDef engineA fill:#064e3b,stroke:#10b981,stroke-width:2px,color:#a7f3d0
    classDef engineB fill:#451a03,stroke:#f59e0b,stroke-width:2px,color:#fde68a
    classDef ui fill:#1e1b4b,stroke:#c084fc,stroke-width:2px,color:#f3e8ff
    classDef db fill:#18181b,stroke:#52525b,stroke-dasharray: 5 5,color:#d4d4d8

    subgraph SANDBOX["PayPal Sandbox Cloud (https://api-m.sandbox.paypal.com)"]
        PP_AUTH["POST /v1/oauth2/token<br/>OAuth 2.0 Bearer Token + Paypal-Debug-Id"]:::paypal
        PP_ORD["POST & PATCH & GET /v2/checkout/orders/{id}<br/>Live 17-Char Orders, 3h TTL Re-Anchoring & Waybill/CE3 Stamps"]:::paypal
        PP_DSP["GET /v1/customer/disputes & GET /v1/reporting/transactions<br/>Live Dispute Queue & 24h Velocity Poll"]:::paypal
    end

    subgraph SDK_LAYER["APIMatic SDK & Context Plugin Layer (paypal_service.py)"]
        CTX[".context-plugins/paypal<br/>Installed via: npx context-plugins install paypal"]:::apimatic
        SDK["PaypalServersdkClient (v2.4.0)<br/>OrdersController (create_order, patch_order, get_order)<br/>TransactionSearchController (search_transactions)"]:::apimatic
    end

    subgraph CORE["ZeroHold Post-Capture Engines (sentinel.py)"]
        EA["Engine A: Relational Visa CE 3.0 & POD Vault<br/>1. SQL Join across 120-365d buyer_history_ledger<br/>2. Enforces 2-of-4 Match Rule (IP / Device Mandatory)<br/>3. Routes UNAUTHORISED vs ITEM_NOT_RECEIVED Webhooks"]:::engineA
        EB["Engine B: Unbacked Exposure & 3PL Attestation Sentinel<br/>1. Monitors 24h GMV Welford Z-Score & Unbacked Captures<br/>2. Stages 3PL WMS Manifests into AG Grid for Inline Edit<br/>3. Syncs Attested Waybills & Auto-Resolves Open INR Claims"]:::engineB
        LEDGER[("SQLite WAL Vault (zerohold.db)<br/>orders_vault · buyer_history_ledger<br/>legitimacy_dossiers · api_audit_log")]:::db
    end

    subgraph FRONTEND["AG Grid Interactive Operations Workbench (server.py on :8080)"]
        GRID["AG Grid v31.3.2 Editable Evidence Vault<br/>• Single-Click Inline Editors (Carrier, Waybill, Wholesale PO)<br/>• Floating Header Filters + Checkbox Selection + Pinned Totals<br/>• Inline [CE3], [INR], [Reset] & [Verify on PayPal] Controls"]:::ui
        MODAL["Human-in-the-Loop Attestation Gate & Printable PDF Packet<br/>POST /api/v1/fulfillment/reconcile<br/>GET /api/dossier/latest/report"]:::ui
    end

    CTX -.->|"Schema & Controller Contracts"| SDK
    SDK <-->|"HTTPS + Paypal-Debug-Id"| PP_AUTH
    SDK <-->|"create / patch / get"| PP_ORD
    SDK <-->|"Velocity & Dispute Telemetry"| PP_DSP

    EA <--> SDK
    EB <--> SDK
    EA <--> LEDGER
    EB <--> LEDGER

    LEDGER --> GRID
    GRID <-->|"Stage 3PL Manifest & Inline Edits"| MODAL
    MODAL --> EB
    GRID -->|"Live GET /api/paypal/order/{id}"| PP_ORD
```

### 2.2 End-to-End Execution Sequence

```mermaid
sequenceDiagram
    autonumber
    actor Ops as Merchant Ops / Judge (:8080)
    participant Grid as AG Grid v31 Workbench (Inline Editable)
    participant API as FastAPI + Sentinel (sentinel.py)
    participant DB as SQLite WAL (orders_vault + buyer_history_ledger)
    participant SDK as APIMatic PayPal SDK (v2.4.0)
    participant PP as PayPal Sandbox (api-m.sandbox.paypal.com)

    Note over Ops,PP: Flow 1: 4.6x Flash-Sale Spike -> 3PL Staging in AG Grid -> Attested PayPal Sync
    Ops->>API: Click "Ingest 5-Order Flash Sale ($17k Unbacked)"
    API->>SDK: TransactionSearchController.search_transactions(24h)
    SDK->>PP: GET /v1/reporting/transactions + GET /v1/customer/disputes
    loop 5 High-Ticket Captures ($17,010 Unbacked Exposure)
        API->>SDK: OrdersController.create_order(intent=CAPTURE)
        SDK->>PP: POST /v2/checkout/orders -> HTTP 201 (Real 17-Char Order ID)
        API->>DB: Run evaluate_ce3_relational_match() against 120-365d buyer_history_ledger
    end
    API-->>Grid: Exposure jumps to 87.1 / 100 · 5 rows show "+ Click or Pull WMS"

    Ops->>Grid: Click "1. Pull 3PL Warehouse Manifest into AG Grid"
    Grid->>Grid: Populates printed FedEx/DHL/UPS waybills as "(STAGED)" & selects checkboxes
    Ops->>Grid: Inline-edit any Carrier dropdown, Waybill, or Wholesale PO cell directly in AG Grid
    Ops->>API: Click "2. Attest & Sync AG Grid Waybills to PayPal" -> Sign Attestation Modal
    loop Each Attested Order
        API->>SDK: OrdersController.patch_order(id, [Patch(op=REPLACE, path=custom_id/description)])
        SDK->>PP: PATCH & GET /v2/checkout/orders/{id} -> HTTP 204 / HTTP 200 OK + Paypal-Debug-Id
    end
    API->>DB: Set Seller Protection = ELIGIBLE_ACTIVE, auto-resolve open INR claims, save Dossier
    API-->>Grid: Exposure drops to 14.3 / 100 (COMPLIANT) in both Dashboard & Printable PDF Report

    Note over Ops,PP: Flow 2: Dual-Reason Webhook Auto-Defense (UNAUTHORISED vs ITEM_NOT_RECEIVED)
    Ops->>API: POST /webhooks/paypal/dispute-created (reason + order_id)
    API->>DB: Query buyer_history_ledger (120-365d) & verify Carrier Waybill/POD state
    alt Eligible (UNAUTHORISED with >=2 CE 3.0 matches OR INR with active Waybill)
        API->>SDK: OrdersController.patch_order & get_order (Stamp DEFENDED|DISPUTE_ID|CE3_OK)
        PP-->>API: HTTP 200 OK (Auto-re-anchors order if 3h Sandbox TTL expired)
        API->>DB: Set dispute_status = AUTO_DEFENDED_PROTECTED
    else Ineligible (UNAUTHORISED with <2 CE 3.0 matches OR INR without Waybill)
        API->>DB: Flag ESCALATED_CE3_EXHAUSTED or ESCALATED_MISSING_WAYBILL
    end
    API-->>Grid: AG Grid flashes updated Dispute Status + logs Paypal-Debug-Id
```

---

## 3. Core Engineering: Engine A & Engine B

### 3.1 Engine A: Relational SQL Visa CE 3.0 Graph Matcher (`db.py` & `sentinel.py`)
Instead of storing a mocked `prior_orders = 3` integer, ZeroHold maintains a relational **`buyer_history_ledger`** table containing historical PayPal captures settled **120 to 365 days ago** and runs a live SQL evaluation (`evaluate_ce3_relational_match`) on every order:

1. **The 2-of-4 Identifier Intersection Rule:** For each historical capture in the `120 to 365 day` window belonging to the buyer, Engine A computes the exact identifier intersection across `buyer_email`, `buyer_ip`, `device_hash`, and `shipping_zip`, enforcing Visa CE 3.0's requirement that at least 2 identifiers match and **at least one match is `buyer_ip` or `device_hash`**.
2. **Prior-Dispute Exclusion (`was_disputed = 0`):** Any historical order that was previously disputed (for example, Sarah Chen's capture `CAP-HIST-5190E` from 240 days ago) is automatically flagged **`✗ EXCLUDED (Previously Disputed)`** in red inside the UI inspector and excluded from the valid CE 3.0 count.
3. **SHA-256 Forensic Hashing (`evidence_sha256`):** At capture and fulfillment, Engine A hashes the order's checkout IP, device fingerprint, matched CE 3.0 capture IDs, and Day-4 carrier GPS coordinates into a tamper-evident SHA-256 digest.
4. **Strict Dual-Reason Webhook Routing (`handle_paypal_dispute_webhook`):**
   * **`UNAUTHORISED` Claims:** Requires $\ge 2$ valid CE 3.0 historical captures (`ce3_ok == True`). Because a fraudster using a stolen card can still receive a package at a drop address, having a carrier waybill alone is not enough to auto-defend an `UNAUTHORISED` claim when CE 3.0 is below 2 prior orders; the system flags **`▲ Escalated (CE3 < 2 Prior)`**.
   * **`MERCHANDISE_OR_SERVICE_NOT_RECEIVED` (`INR`) Claims:** The buyer admits placing the order but claims the courier never delivered it. This does not require CE 3.0 history; it requires **Carrier Tracking + Archived Day-4 GPS Proof of Delivery (`has_waybill == True`)**. If an `INR` webhook hits an unshipped flash-sale order, it flags **`▲ Escalated (No Waybill)`**, and automatically resolves to **`✓ Auto-Defended (GPS POD)`** once the merchant syncs the waybill.

### 3.2 Engine B: Welford Velocity Math, 3PL Staging & Anti-Gaming Security

#### Mathematical Formulation
Engine B evaluates the merchant's 24-hour GMV against their 30-day rolling baseline ($\mu_{\text{GMV}} = 4,000\text{ USD/day}$, $\sigma_{\text{GMV}} = 620\text{ USD}$):

$$Z_{\text{GMV}} = \max\left(0, \frac{\text{GMV}_{24\text{h}} - \mu_{\text{GMV}}}{\sigma_{\text{GMV}}}\right)$$

The composite **Unbacked Capture & Reserve Exposure Score** $\in [4.0, 99.0]$ is computed as:

$$\text{ExposureScore} = \underbrace{\min(3.8 \cdot Z_{\text{GMV}}, 42.0) \cdot \gamma_{\text{attested}}}_{\text{Velocity Anomaly Component}} + \underbrace{52.0 \cdot \left(\frac{N_{\text{untracked}}}{N_{\text{total}}}\right)}_{\text{Unbacked Capture Ratio}} + \underbrace{\min\left(14.0 \cdot \frac{R_{\text{dispute}}}{1.50\%}, 14.0\right)}_{\text{VAMP / Dispute Cliff Proximity}}$$

where $\gamma_{\text{attested}} = 0.15$ only after the merchant completes the **Human-in-the-Loop Waybill & Supplier PO Attestation** and PayPal's Sandbox server confirms `HTTP 200 OK` across all synced orders ($\gamma_{\text{attested}} = 1.0$ otherwise).

* **During a $4.6\times$ Flash-Sale Surge (`$18,450` GMV, $Z = +23.31\sigma$, 5 of 7 orders unbacked):**

$$\text{ExposureScore} = 42.0 + 52.0 \cdot \left(\frac{5}{7}\right) + 8.0 = \mathbf{87.1 / 100} \quad (\text{ACTION REQUIRED // 17k USD UNBACKED EXPOSURE})$$
* **After 3PL Manifest Pull, Inline AG Grid Review & PayPal Sync (0 untracked orders, 100% Seller Protection active):**

$$\text{ExposureScore} = (42.0 \times 0.15) + 0.0 + 8.0 = \mathbf{14.3 / 100} \quad (\text{COMPLIANT // 100\% FULFILLMENT AND PO BACKED})$$

#### Adversarial Security: Why Bust-Out Scammers Cannot Game ZeroHold ("Threshold Surfing" Defense)
A critical risk-engineering question is whether exposing an account exposure gauge helps bust-out scammers stay just below PayPal's freeze threshold. ZeroHold prevents threshold surfing through three mechanisms:
1. **No Private Underwriting Oracle:** ZeroHold does not leak secret internal PayPal risk weights; it computes exposure strictly from the merchant's own unshipped backlog dollars, their own 30-day GMV standard deviation, and Visa/PayPal's public **1.50% dispute cap**.
2. **Physical Proof-of-Work Required to Lower Exposure:** Over 60% of the exposure score is tied to the **Unbacked Capture Ratio**. A scammer with no physical inventory cannot lower their score because PayPal's Seller Protection engine cross-verifies carrier tracking numbers against live FedEx/UPS/DHL hub scans (`IN_TRANSIT` / `DELIVERED`) before releasing reserve holds.
3. **Human-in-the-Loop Legal Attestation + Resolution Center Packet:** Lowering the velocity anomaly penalty requires the merchant officer to attest to specific **Paid Wholesale Distributor Invoice IDs (`PO-RED-2026-8841`, `PO-DJI-2026-8842`, etc.)** and warehouse bin counts, generating a signed PDF packet (`GET /api/dossier/latest/report`) for human underwriting review in the PayPal Resolution Center.

---

## 4. Deterministic 4-Scenario Demo Matrix

You can test and verify all four real-world post-capture dispute and fulfillment outcomes on `http://localhost:8080`:

| Demo Scenario | Target Order Row in AG Grid | Buyer's 120-365d SQL Ledger & Waybill State | Action to Click | Deterministic Production Result |
| :--- | :--- | :--- | :--- | :--- |
| **1. `UNAUTHORISED` Auto-Defense (Visa CE 3.0 Win)** | **Arjun Mehta** (`$800.00 CAM-4K-PRO`) *or* **Vikram Rao** (`$3,450 RED-KOMODO-KIT`) | **`✓ 3 Settled (CE 3.0 OK)`** (`CAP-HIST-4410A`, `3892B`, `2104C` matching IP, Device & Zip) | Click inline **`[CE3]`** button | **`✓ Auto-Defended (CE 3.0 SQL)`** — Stamps matched historical captures onto PayPal Sandbox (`HTTP 200`). |
| **2. `UNAUTHORISED` Escalation (Prior Dispute Exclusion)** | **Sarah Chen** (`$640.00 LENS-35MM-F14`) *or* **Neha Kapoor** (`$3,150 GIMBAL-RS4-PRO`) | **`✗ 1 Settled (Min 2)`** (Sarah has 2 historical orders, but `CAP-HIST-5190E` was disputed 240d ago and is excluded in red) | Click inline **`[CE3]`** button | **`▲ Escalated (CE3 < 2 Prior)`** — Refuses to auto-defend because buyer has fewer than 2 undisputed 120-365d orders. |
| **3. `ITEM_NOT_RECEIVED` Auto-Defense (Carrier GPS POD Win)** | **Sarah Chen** (`$640.00 LENS-35MM-F14`) | Has active **DHL Waybill `#4491028471`** + archived Day-4 Front-Desk GPS POD | Click **`[↻]`** to clear Scenario 2, then click **`[INR]`** | **`✓ Auto-Defended (GPS POD)`** — Even with `<2` CE 3.0 orders, `INR` auto-defends 100% via signed DHL delivery proof. |
| **4. `ITEM_NOT_RECEIVED` on Unshipped Flash-Sale Order $\rightarrow$ Resolved by 3PL Sync** | Any of the **5 Flash-Sale Orders** after clicking `Ingest 5-Order Flash Sale` | Starts with **`+ Click or Pull WMS`** (No carrier waybill synced yet) | 1. Click **`[INR]`** on unshipped row<br/>2. Click **`1. Pull 3PL Warehouse Manifest`**<br/>3. Click **`2. Attest & Sync AG Grid Waybills`** | 1. Immediately flags **`▲ Escalated (No Waybill)`**.<br/>2. Pulling the 3PL manifest into AG Grid and syncing to PayPal Sandbox **auto-resolves** the open claim to **`✓ Auto-Defended (GPS POD)`**! |

---

## 5. Sponsor Track Implementations: APIMatic & AG Grid

### 5.1 Best Use of APIMatic (`paypal-server-sdk==2.4.0` + Context Plugin)

| APIMatic Integration Artifact | File & Method in Repo | Production Role |
| :--- | :--- | :--- |
| **APIMatic Context Plugin for PayPal** | `.context-plugins/paypal/` (installed via `npx context-plugins install paypal`) | Provides the official APIMatic SDK controller contracts, model schemas (`OrderRequest`, `Patch`, `PatchOp`), and OAuth 2.0 patterns directly in the repository. |
| **`PaypalServersdkClient` & `ClientCredentialsAuthCredentials`** | `paypal_service.py` (`__init__`) | Initializes authenticated Sandbox client sessions (`Environment.SANDBOX`) with automatic `.envrc` / `.env` credential loading. |
| **`OrdersController.create_order`** | `paypal_service.py` (`create_real_sandbox_order`) | Mints genuine 17-character PayPal Sandbox Orders (`POST /v2/checkout/orders`) using typed `OrderRequest`, `PurchaseUnitRequest`, and `AmountWithBreakdown` SDK models. |
| **`OrdersController.patch_order` (`Patch` + `PatchOp.REPLACE`)** | `paypal_service.py` (`sync_order_tracking_on_sandbox`) | Executes RFC 6902 JSON Patch operations through APIMatic's `OrdersController` to write `PROTECTED\|CARRIER:WAYBILL\|SUPPLIER_PO` and `DEFENDED\|...` stamps onto live PayPal Sandbox orders. |
| **`OrdersController.get_order`** | `paypal_service.py` (`fetch_live_order_from_paypal`) | Reads back the mutated Order JSON directly from PayPal's Sandbox server for read-after-write verification and the in-grid `Verify on PayPal` inspector modal. |
| **`TransactionSearchController.search_transactions`** | `paypal_service.py` (`check_transaction_velocity`) | Polls 24-hour transaction velocity windows (`GET /v1/reporting/transactions`) prior to Welford Z-score evaluation. |
| **Automatic Sandbox 3-Hour TTL Re-Anchoring & `HTTP 200` Gate** | `paypal_service.py` (`sync_order_tracking_on_sandbox`, `submit_friendly_fraud_evidence`) | If an unapproved Sandbox order ages past PayPal's 3-hour TTL (`HTTP 404`), the service automatically mints a fresh Sandbox order via APIMatic, updates the foreign key in SQLite, and gates local status updates strictly on `HTTP 200 OK`. |

### 5.2 Best Use of AG Grid (`server.py` — `ag-theme-quartz-dark`)

* **Single-Click Inline Cell Editing (`editable: true`, `singleClickEdit: true`):** Operations teams can click directly on any `Wholesale PO`, `Carrier`, or `Waybill` cell inside AG Grid to edit values inline using `agSelectCellEditor` (`FEDEX`, `DHL`, `UPS`, `BLUEDART`) and `agTextCellEditor`. Edited cells automatically stage in amber (`(STAGED)`) via `onCellValueChanged` before syncing to PayPal.
* **Floating Column Header Filters (`floatingFilter: true`):** Every primary column includes a live sub-header filter (`agNumberColumnFilter` on `Amount` for expressions like `>3000`, and `agTextColumnFilter` on `PayPal Order ID`, `Product & SKU`, `Wholesale PO`, and `Waybill`).
* **Multi-Row Checkbox Selection & 3PL Manifest Staging:** Clicking `1. Pull 3PL Warehouse Manifest into AG Grid` programmatically populates pending warehouse tracking numbers across all untracked grid nodes (`node.setDataValue`), selects their checkboxes, and triggers `enableCellChangeFlash`.
* **Compact Multi-Line Wrapping & 150ms Hover Tooltips (`wrapText: true`, `autoHeight: true`):** Custom CSS overrides (`line-height: 1.35`, `--ag-row-height: 36px`) keep wrapped two-line cells compact while displaying full order metadata on hover.
* **Pinned Bottom Summary Row (`pinnedBottomRowData`):** Continuously totals 24h GMV, Seller-Protected dollar volume (`%`), and remaining unbacked captures at the bottom of the grid.

---

## 6. FastAPI REST API Reference & SQLite WAL Schema

### 6.1 Production & Test-Harness Endpoints (`server.py`)

| Method & Route | Purpose | Outbound PayPal Sandbox Calls |
| :--- | :--- | :--- |
| `GET /` | Renders the AG Grid Merchant Treasury & Seller Protection Workbench UI. | Mints 2 baseline Sandbox orders if `orders_vault` is empty. |
| `GET /api/state` | Returns live Welford metrics, Exposure Score, orders with relational CE 3.0 matches, latest dossier, and APIMatic audit logs. | None (reads from SQLite WAL). |
| `POST /api/v1/fulfillment/reconcile` | **Production Human-in-the-Loop Gate:** Accepts inline-edited AG Grid waybills, supplier POs, hub manifest, and officer attestation; syncs to PayPal Sandbox; auto-resolves open `INR` disputes; compiles the Underwriting Dossier. | `N x OrdersController.patch_order` & `GET /v2/checkout/orders/{id}` (with automatic 404 TTL re-anchoring). |
| `POST /webhooks/paypal/dispute-created` | **Production Webhook Receiver (`CUSTOMER.DISPUTE.CREATED`):** Evaluates `UNAUTHORISED` (via SQL CE 3.0 match) or `MERCHANDISE_OR_SERVICE_NOT_RECEIVED` (via Carrier POD) for any `order_id`. | `PATCH & GET /v2/checkout/orders/{id}` (if eligible for auto-defense). |
| `POST /api/orders/{order_id}/reset-dispute` | Clears the dispute state on a single order row so judges can test multiple webhook types on the same order. | None (updates `orders_vault`). |
| `GET /api/paypal/order/{order_id}` | Live verification proxy that executes `OrdersController.get_order` against `api-m.sandbox.paypal.com` for the in-grid modal. | `OrdersController.get_order` (`GET /v2/checkout/orders/{order_id}`) |
| `GET /api/dossier/latest/report` | Renders the printable/PDF-ready **PayPal Pre-Freeze Account Legitimacy & Fulfillment Dossier** (matching the dashboard exposure score 1:1). | None (renders collated dossier). |
| `POST /api/simulate/flash-sale` | Test Harness: Ingests 5 high-ticket Sandbox orders without tracking (`$17,010` unbacked exposure). | `TransactionSearchController.search_transactions`, `GET /v1/customer/disputes`, `5x OrdersController.create_order` |
| `POST /api/simulate/live-sandbox-order` | Test Harness: Mints 1 live Sandbox order via APIMatic SDK, rotating across 4 distinct SKUs and buyer personas. | `OrdersController.create_order`, `OrdersController.patch_order`, `GET /v2/checkout/orders/{id}` |
| `POST /api/reset` | Clears local SQLite tables, re-seeds `buyer_history_ledger`, and mints 2 fresh baseline orders on PayPal Sandbox. | `2x OrdersController.create_order`, `2x OrdersController.patch_order & GET` |

### 6.2 SQLite WAL Database Schema (`db.py` -> `zerohold.db`)

1. **`orders_vault`**: `order_id` (PK, 17-char PayPal Sandbox ID), `capture_id`, `buyer_email`, `amount_usd`, `sku`, `item_name`, `buyer_ip`, `device_hash`, `shipping_zip`, `policy_version`, `prior_undisputed_orders`, `ce3_matched_captures_json`, `evidence_sha256`, `carrier`, `tracking_number`, `delivery_status`, `gps_proof`, `seller_protection`, `evidence_readiness_pct`, `dispute_id`, `dispute_reason`, `dispute_status`, `captured_at`.
2. **`buyer_history_ledger`**: `hist_capture_id` (PK), `paypal_order_id`, `buyer_email`, `amount_usd`, `sku`, `buyer_ip`, `device_hash`, `shipping_zip`, `settled_days_ago` (`120-365`), `was_disputed` (`0` or `1`).
3. **`legitimacy_dossiers`**: `dossier_id` (PK), `created_at`, `freeze_risk_before`, `freeze_risk_after`, `gmv_24h`, `baseline_gmv`, `z_score`, `synced_orders_count`, `supplier_po_ref`, `carrier_manifest_ref`, `campaign_utm_ref`, `dispatch_sla_pct`, `dossier_json`.
4. **`api_audit_log`**: `id` (PK), `ts`, `engine`, `sdk_component`, `endpoint`, `http_status`, `latency_ms`, `summary` (with `Paypal-Debug-Id`), `payload_json`.

---

## 7. Quickstart & Independent `curl` Verification Against `api-m.sandbox.paypal.com`

### Step 1: Configure PayPal Sandbox Credentials
Create a `.envrc` or `.env` file in `/home/errcee/atErrCee/Hackathons/merchant-aegis` with your PayPal Developer Sandbox credentials:

```bash
export PAYPAL_CLIENT_ID="your_sandbox_client_id"
export PAYPAL_CLIENT_SECRET="your_sandbox_client_secret"
```

### Step 2: Install Dependencies & Mirror the APIMatic Context Plugin

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
npx context-plugins install paypal
mkdir -p .context-plugins && cp -r ~/.context-plugins/vscode/paypal .context-plugins/paypal
```

### Step 3: Start the Workbench (`http://localhost:8080`)

```bash
./.venv/bin/python server.py
```

### Step 4: Verify Any AG Grid Order Directly on PayPal's Sandbox Cloud
Every Order ID in the AG Grid table is a real Orders v2 resource stored on PayPal's servers. Because headless Sandbox orders sit in `CREATED` state without a browser buyer-login popup, ZeroHold persists carrier waybills, wholesale supplier POs, and Visa CE 3.0 audit stamps inside `purchase_units[0].custom_id` (`PROTECTED|FEDEX:...|PO-...` and `DEFENDED|PP-D-...|CE3_OK:3`) and `description` via `PATCH /v2/checkout/orders/{id}`.

Click **`Verify on PayPal`** on any row in AG Grid to inspect the live JSON response and `Paypal-Debug-Id` directly from PayPal's servers, or run this `curl` command in your terminal:

```bash
TOKEN=$(curl -s -u "$PAYPAL_CLIENT_ID:$PAYPAL_CLIENT_SECRET" \
  https://api-m.sandbox.paypal.com/v1/oauth2/token \
  -d "grant_type=client_credentials" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -s -H "Authorization: Bearer $TOKEN" \
  https://api-m.sandbox.paypal.com/v2/checkout/orders/<PASTE_ORDER_ID_FROM_AG_GRID> | python3 -m json.tool
```
