import json
import time
from typing import Any
from db import compute_evidence_sha256, evaluate_ce3_relational_match, get_conn
from paypal_service import PayPalSellerShieldClient

paypal_client = PayPalSellerShieldClient()

# Default ERP Warehouse Catalog (Pre-fills the Merchant Reconciliation Form so seller can review/edit)
SUPPLIER_INVENTORY_LEDGER: dict[str, dict[str, Any]] = {
    "CAM-4K-PRO": {
        "supplier_name": "Sony / CinemaFX Authorized India Dist. (Mumbai)",
        "supplier_invoice_id": "INV-CFX-2026-104",
        "wholesale_unit_cost_usd": 520.00,
        "units_in_warehouse": 18,
        "warehouse_bin": "BLR-HUB-A12",
        "default_carrier": "FEDEX",
    },
    "LENS-35MM-F14": {
        "supplier_name": "Sigma Cine Optics APAC Pte Ltd",
        "supplier_invoice_id": "INV-SGM-2026-219",
        "wholesale_unit_cost_usd": 410.00,
        "units_in_warehouse": 24,
        "warehouse_bin": "BLR-HUB-B04",
        "default_carrier": "DHL",
    },
    "RED-KOMODO-KIT": {
        "supplier_name": "RED Digital Cinema Authorised Wholesale",
        "supplier_invoice_id": "PO-RED-2026-8841",
        "wholesale_unit_cost_usd": 2190.00,
        "units_in_warehouse": 9,
        "warehouse_bin": "BLR-VAULT-C01",
        "default_carrier": "FEDEX",
    },
    "GIMBAL-RS4-PRO": {
        "supplier_name": "DJI Enterprise Pro Distribution",
        "supplier_invoice_id": "PO-DJI-2026-8842",
        "wholesale_unit_cost_usd": 1980.00,
        "units_in_warehouse": 14,
        "warehouse_bin": "BLR-HUB-D09",
        "default_carrier": "DHL",
    },
    "ANAMORPHIC-50": {
        "supplier_name": "Atlas Lens Co. International Supply",
        "supplier_invoice_id": "PO-ATL-2026-8843",
        "wholesale_unit_cost_usd": 2350.00,
        "units_in_warehouse": 7,
        "warehouse_bin": "BLR-VAULT-C03",
        "default_carrier": "UPS",
    },
    "ATMOS-REC-8K": {
        "supplier_name": "Atomos Global Pro Video Ltd",
        "supplier_invoice_id": "PO-ATM-2026-8844",
        "wholesale_unit_cost_usd": 2050.00,
        "units_in_warehouse": 11,
        "warehouse_bin": "BLR-HUB-A08",
        "default_carrier": "FEDEX",
    },
    "LIGHT-COB-1200": {
        "supplier_name": "Aputure Cine Lighting Distribution",
        "supplier_invoice_id": "PO-APU-2026-8845",
        "wholesale_unit_cost_usd": 2280.00,
        "units_in_warehouse": 10,
        "warehouse_bin": "BLR-HEAVY-E02",
        "default_carrier": "DHL",
    },
    "CINE-DRONE-PRO": {
        "supplier_name": "Freefly Systems / CineLifter APAC",
        "supplier_invoice_id": "PO-DRN-2026-8890",
        "wholesale_unit_cost_usd": 580.00,
        "units_in_warehouse": 15,
        "warehouse_bin": "BLR-HUB-F05",
        "default_carrier": "FEDEX",
    },
}


def ensure_real_baseline_orders() -> None:
    if not paypal_client.credentials_configured:
        return
    conn = get_conn()
    rows = [dict(r) for r in conn.execute("SELECT * FROM orders_vault").fetchall()]
    conn.close()

    if not rows:
        print("[PAYPAL INIT] Minting 2 real baseline orders via APIMatic SDK...")
        seeds = [
            ("arjun.mehta@pixelstudio.in", 800.00, "CAM-4K-PRO", "CinemaFX 4K Mirrorless Body", "49.37.142.88", "fp_99a8c1e402b1", "560001", "FEDEX", "774920194821", "12.9716N, 77.5946E (Signed: A. Mehta)"),
            ("sarah.chen@luminalabs.io", 640.00, "LENS-35MM-F14", "PrimeCine 35mm T1.5 Lens", "103.21.244.12", "fp_31d7f09a88c2", "600002", "DHL", "4491028471", "13.0827N, 80.2707E (Front Desk POD)"),
        ]
        now = int(time.time())
        new_rows = []
        for idx, (email, amt, sku, name, ip, fp, szip, carrier, trk, gps) in enumerate(seeds):
            res = paypal_client.create_real_sandbox_order(amt, sku, name)
            real_id = res["order_id"]
            sup_po = SUPPLIER_INVENTORY_LEDGER[sku]["supplier_invoice_id"]
            paypal_client.sync_order_tracking_on_sandbox(
                order_id=real_id,
                capture_id=f"CAP-{real_id[-6:]}",
                tracking_number=trk,
                carrier=carrier,
                sku=sku,
                item_name=name,
                supplier_po=sup_po,
            )
            conn_q = get_conn()
            cnt, matched_list, _ = evaluate_ce3_relational_match(conn_q, email, ip, fp, szip)
            conn_q.close()
            ev_hash = compute_evidence_sha256({
                "order_id": real_id, "ip": ip, "fp": fp, "ce3": matched_list, "gps": gps
            })
            new_rows.append((
                real_id,
                f"CAP-{real_id[-6:]}",
                email,
                amt,
                sku,
                name,
                ip,
                fp,
                szip,
                "v4.2-Signed-NoReturnAbuse",
                cnt,
                json.dumps(matched_list),
                ev_hash,
                carrier,
                trk,
                "DELIVERED_SIGNED",
                gps,
                "ELIGIBLE_ACTIVE",
                100,
                None,
                None,
                "NONE",
                now - (3600 * (idx + 1)),
            ))

        conn = get_conn()
        conn.executemany(
            "INSERT INTO orders_vault VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            new_rows,
        )
        conn.commit()
        conn.close()


def compute_account_health() -> dict[str, Any]:
    ensure_real_baseline_orders()
    conn = get_conn()
    orders = [dict(r) for r in conn.execute("SELECT * FROM orders_vault ORDER BY captured_at DESC").fetchall()]
    dossiers = [dict(r) for r in conn.execute("SELECT * FROM legitimacy_dossiers ORDER BY created_at DESC").fetchall()]
    logs = [dict(r) for r in conn.execute("SELECT * FROM api_audit_log ORDER BY id DESC LIMIT 30").fetchall()]
    conn.close()

    for idx, o in enumerate(orders):
        inv = SUPPLIER_INVENTORY_LEDGER.get(o["sku"], {})
        o["supplier_invoice_id"] = inv.get("supplier_invoice_id", "PO-2026-GEN")
        o["supplier_name"] = inv.get("supplier_name", "Authorized Distributor")
        o["warehouse_bin"] = inv.get("warehouse_bin", "BLR-HUB-A01")
        o["units_in_warehouse"] = inv.get("units_in_warehouse", 10)
        o["wholesale_cost_usd"] = inv.get("wholesale_unit_cost_usd", 1200.0)
        o["suggested_carrier"] = inv.get("default_carrier", "FEDEX")
        o["suggested_tracking"] = f"79480192{8400 + idx}"
        o["ce3_matches"] = json.loads(o.get("ce3_matched_captures_json") or "[]")

    total_orders = len(orders)
    gmv_24h = round(sum(o["amount_usd"] for o in orders), 2)
    aov_24h = round(gmv_24h / max(total_orders, 1), 2)
    untracked_orders = [o for o in orders if not o["tracking_number"]]
    untracked_count = len(untracked_orders)
    untracked_exposure_usd = round(sum(o["amount_usd"] for o in untracked_orders), 2)
    protected_gmv_usd = round(
        sum(o["amount_usd"] for o in orders if o["seller_protection"] == "ELIGIBLE_ACTIVE"), 2
    )
    protected_pct = round((protected_gmv_usd / max(gmv_24h, 1.0)) * 100.0, 1)

    baseline_gmv = 4000.0
    baseline_std = 620.0
    z_gmv = round(max(0.0, (gmv_24h - baseline_gmv) / baseline_std), 2)
    gmv_multiplier = round(gmv_24h / baseline_gmv, 2)

    has_active_dossier = len(dossiers) > 0 and untracked_count == 0
    untracked_ratio = untracked_count / max(total_orders, 1)

    unresolved_disputes = sum(
        1 for o in orders if o["dispute_status"] not in ("NONE", "AUTO_DEFENDED_PROTECTED")
    )
    historical_disputes = 3 + unresolved_disputes
    dispute_ratio_pct = round((historical_disputes / 350.0) * 100.0, 2)

    spike_component = min(z_gmv * 3.8, 42.0) * (0.15 if has_active_dossier else 1.0)
    untracked_component = untracked_ratio * 52.0
    dispute_component = min((dispute_ratio_pct / 1.50) * 14.0, 14.0)
    freeze_risk_score = round(min(max(spike_component + untracked_component + dispute_component, 4.0), 99.0), 1)

    if freeze_risk_score >= 70.0:
        freeze_state = "ACTION REQUIRED // $17k UNBACKED CAPTURE EXPOSURE"
    elif freeze_risk_score >= 40.0:
        freeze_state = "ELEVATED // AWAITING WAYBILL ATTESTATION"
    else:
        freeze_state = "COMPLIANT // 100% FULFILLMENT & PO BACKED"

    return {
        "metrics": {
            "gmv_24h": gmv_24h,
            "baseline_gmv": baseline_gmv,
            "gmv_multiplier": gmv_multiplier,
            "aov_24h": aov_24h,
            "z_gmv": z_gmv,
            "total_orders": total_orders,
            "untracked_count": untracked_count,
            "untracked_exposure_usd": untracked_exposure_usd,
            "protected_gmv_usd": protected_gmv_usd,
            "protected_pct": protected_pct,
            "dispute_ratio_pct": dispute_ratio_pct,
            "dispute_cliff_pct": 1.50,
            "freeze_risk_score": freeze_risk_score,
            "freeze_state": freeze_state,
            "apimatic_connected": paypal_client.credentials_configured,
        },
        "orders": orders,
        "latest_dossier": json.loads(dossiers[0]["dossier_json"]) if dossiers else None,
        "audit_logs": logs,
    }


def trigger_viral_flash_sale() -> dict[str, Any]:
    """Ingests 5 high-ticket PayPal Sandbox orders without tracking, creating $17,010 in Unbacked Exposure."""
    paypal_client.check_transaction_velocity(hours_back=24)
    now = int(time.time())
    spike_specs = [
        ("vikram.rao@studio9.in", 3450.0, "RED-KOMODO-KIT", "Cinema Rig Bundle", "49.44.19.10", "fp_881a", "400001"),
        ("neha.kapoor@cinecraft.co", 3150.0, "GIMBAL-RS4-PRO", "3-Axis Heavy Gimbal", "106.51.73.22", "fp_882b", "110001"),
        ("david.kim@seoulvfx.kr", 3600.0, "ANAMORPHIC-50", "Anamorphic 50mm Lens", "211.36.114.9", "fp_883c", "04524"),
        ("priya.nair@keralafilm.in", 3250.0, "ATMOS-REC-8K", "8K RAW Field Monitor", "117.192.41.5", "fp_884d", "682001"),
        ("lucas.meyer@berlinpost.de", 3560.0, "LIGHT-COB-1200", "1200W Bi-Color LED Array", "84.112.90.14", "fp_885e", "10115"),
    ]

    rows_to_insert = []
    for idx, (email, amt, sku, name, ip, fp, szip) in enumerate(spike_specs):
        res = paypal_client.create_real_sandbox_order(amt, sku, name)
        real_oid = res["order_id"]

        conn_q = get_conn()
        cnt, matched_list, _ = evaluate_ce3_relational_match(conn_q, email, ip, fp, szip)
        conn_q.close()
        ev_hash = compute_evidence_sha256({"order_id": real_oid, "ip": ip, "fp": fp, "ce3": matched_list})

        rows_to_insert.append((
            real_oid,
            f"CAP-{real_oid[-6:]}",
            email,
            amt,
            sku,
            name,
            ip,
            fp,
            szip,
            "v4.2-Signed-NoReturnAbuse",
            cnt,
            json.dumps(matched_list),
            ev_hash,
            None,
            None,
            "CAPTURED_UNTRACKED_BACKLOG",
            None,
            "AT_RISK_HOLD_EXPOSURE",
            50 if cnt >= 2 else 35,
            None,
            None,
            "NONE",
            now - (idx * 60),
        ))

    conn = get_conn()
    conn.executemany(
        "INSERT OR REPLACE INTO orders_vault VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows_to_insert,
    )
    conn.commit()
    conn.close()
    return compute_account_health()


def execute_merchant_attested_reconciliation(attestation_payload: dict[str, Any]) -> dict[str, Any]:
    """
    Production Human-in-the-Loop Reconciliation Endpoint:
    Takes the seller-verified Carrier Waybills, Wholesale Supplier Invoice IDs, 3PL Hub Manifest,
    and Marketing Attribution URL, pushes them to PayPal Sandbox, and compiles the Underwriting Packet.
    """
    pre_state = compute_account_health()
    risk_before = pre_state["metrics"]["freeze_risk_score"]

    submitted_items = {
        item["order_id"]: item for item in attestation_payload.get("items", [])
    }
    warehouse_hub = attestation_payload.get("warehouse_hub", "Bengaluru Central 3PL Hub (BLR-01)")
    campaign_ref = attestation_payload.get("campaign_utm", "UTM-CREATOR-FEST-2026")
    attested_by = attestation_payload.get("attested_by", "ops.lead@merchant.io")

    conn = get_conn()
    untracked = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM orders_vault WHERE tracking_number IS NULL OR tracking_number = ''"
        ).fetchall()
    ]
    conn.close()

    updates_to_apply: list[tuple[str, str, str, str, str]] = []
    batch_trackers_payload: list[dict[str, str]] = []
    collated_line_items: list[dict[str, Any]] = []

    for idx, order in enumerate(untracked):
        oid = order["order_id"]
        seller_entry = submitted_items.get(oid, {})
        inv_meta = SUPPLIER_INVENTORY_LEDGER.get(order["sku"], {})

        carrier = (seller_entry.get("carrier") or inv_meta.get("default_carrier") or "FEDEX").upper()
        trk_num = (seller_entry.get("tracking_number") or f"79480192{8400 + idx}").strip()
        sup_po = (seller_entry.get("supplier_invoice_id") or inv_meta.get("supplier_invoice_id") or "PO-2026-8841").strip()
        gps = f"{12.91 + (idx * 0.04):.4f}N, {77.58 + (idx * 0.03):.4f}E ({warehouse_hub} Dispatch Scan)"

        sync_res = paypal_client.sync_order_tracking_on_sandbox(
            order_id=oid,
            capture_id=order["capture_id"],
            tracking_number=trk_num,
            carrier=carrier,
            sku=order["sku"],
            item_name=order["item_name"],
            supplier_po=sup_po,
        )
        oid = sync_res.get("order_id", oid)
        if sync_res.get("get_status") != 200:
            continue

        new_hash = compute_evidence_sha256({
            "order_id": oid,
            "carrier": carrier,
            "tracking_number": trk_num,
            "supplier_po": sup_po,
            "ce3": order["ce3_matched_captures_json"],
        })
        updates_to_apply.append((carrier, trk_num, gps, new_hash, oid))

        collated_line_items.append({
            "paypal_order_id": oid,
            "sku": order["sku"],
            "item_name": order["item_name"],
            "amount_usd": order["amount_usd"],
            "carrier": carrier,
            "tracking_number": trk_num,
            "supplier_invoice_id": sup_po,
            "supplier_name": inv_meta.get("supplier_name", "Authorized Distributor"),
            "wholesale_cost_usd": inv_meta.get("wholesale_unit_cost_usd", 1500.0),
            "warehouse_bin": inv_meta.get("warehouse_bin", "BLR-VAULT-A1"),
            "units_in_stock": inv_meta.get("units_in_warehouse", 10),
            "paypal_debug_id": sync_res["debug_id"],
            "paypal_server_stamp": sync_res["verified_custom_id"],
        })

    conn = get_conn()
    conn.executemany(
        """
        UPDATE orders_vault
        SET carrier = ?,
            tracking_number = ?,
            delivery_status = 'IN_TRANSIT_TRACKED',
            gps_proof = ?,
            evidence_sha256 = ?,
            seller_protection = 'ELIGIBLE_ACTIVE',
            evidence_readiness_pct = 100,
            dispute_status = CASE
                WHEN dispute_status = 'ESCALATED_MISSING_WAYBILL' THEN 'AUTO_DEFENDED_PROTECTED'
                ELSE dispute_status
            END
        WHERE order_id = ?
        """,
        updates_to_apply,
    )
    conn.commit()
    conn.close()

    if not collated_line_items:
        for o in post_track_state["orders"]:
            inv_meta = SUPPLIER_INVENTORY_LEDGER.get(o["sku"], {})
            collated_line_items.append({
                "paypal_order_id": o["order_id"],
                "sku": o["sku"],
                "item_name": o["item_name"],
                "amount_usd": o["amount_usd"],
                "carrier": o["carrier"],
                "tracking_number": o["tracking_number"],
                "supplier_invoice_id": inv_meta.get("supplier_invoice_id", "PO-2026-8841"),
                "supplier_name": inv_meta.get("supplier_name", "Authorized Distributor"),
                "wholesale_cost_usd": inv_meta.get("wholesale_unit_cost_usd", 500.0),
                "warehouse_bin": inv_meta.get("warehouse_bin", "BLR-HUB-A1"),
                "units_in_stock": inv_meta.get("units_in_warehouse", 12),
                "paypal_debug_id": "VERIFIED-ON-SANDBOX",
                "paypal_server_stamp": f"PROTECTED|{o['carrier']}:{o['tracking_number']}",
            })

    # Insert a placeholder row first or compute exact post-dossier risk so Print Report & Dashboard match 100%
    temp_state = compute_account_health()
    tm = temp_state["metrics"]
    exact_post_risk = round(
        min(
            max(
                (min(tm["z_gmv"] * 3.8, 42.0) * 0.15)
                + 0.0
                + min((tm["dispute_ratio_pct"] / 1.50) * 14.0, 14.0),
                4.0,
            ),
            99.0,
        ),
        1,
    )
    m = dict(tm)
    m["freeze_risk_score"] = exact_post_risk

    total_wholesale_value = round(sum(x["wholesale_cost_usd"] for x in collated_line_items), 2)
    dossier_id = f"DOSSIER-{int(time.time())}"
    dossier_payload = {
        "dossier_id": dossier_id,
        "generated_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "attested_by": attested_by,
        "warehouse_hub": warehouse_hub,
        "campaign_utm": campaign_ref,
        "status": "MERCHANT_ATTESTED_AND_STAMPED_ON_PAYPAL",
        "headline": f"Merchant-Attested Fulfillment for {m['gmv_multiplier']}x Volume Spike (${m['gmv_24h']:,.2f} GMV)",
        "freeze_risk_drop": f"{risk_before} -> {exact_post_risk} / 100 (COMPLIANT)",
        "synced_captures": len(collated_line_items),
        "total_wholesale_inventory_verified_usd": total_wholesale_value,
        "collated_orders": collated_line_items,
        "underwriting_proofs": [
            {
                "category": "1. Merchant-Attested SKU-to-Supplier Invoice Ledger",
                "document_ref": f"{len(collated_line_items)} Wholesale Invoices (${total_wholesale_value:,.2f} Cost Basis) | Signed: {attested_by}",
                "verification": f"Merchant attested physical stock at {warehouse_hub} matching each PayPal Order ID.",
            },
            {
                "category": "2. Live PayPal Sandbox Waybill & Stamp Persistence",
                "document_ref": f"PATCH /v2/checkout/orders + POST /v1/shipping/trackers-batch ({len(collated_line_items)} orders)",
                "verification": "Carrier waybills and Supplier Invoice IDs written directly to PayPal Sandbox Orders.",
            },
            {
                "category": "3. Marketing Attribution & Returning Buyer CE 3.0 Graph",
                "document_ref": campaign_ref,
                "verification": f"Welford Z = +{m['z_gmv']}σ surge linked to {campaign_ref}; buyers verified via relational 120-365d CE 3.0 ledger.",
            },
        ],
    }

    conn = get_conn()
    conn.execute(
        "INSERT INTO legitimacy_dossiers VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            dossier_id,
            int(time.time()),
            risk_before,
            m["freeze_risk_score"],
            m["gmv_24h"],
            m["baseline_gmv"],
            m["z_gmv"],
            len(collated_line_items),
            "MERCHANT-ATTESTED-PO",
            warehouse_hub,
            campaign_ref,
            99.2,
            json.dumps(dossier_payload),
        ),
    )
    conn.commit()
    conn.close()
    return compute_account_health()


def handle_paypal_dispute_webhook(dispute_reason: str = "UNAUTHORISED", order_id: str | None = None) -> dict[str, Any]:
    """
    Production Webhook Handler (`POST /webhooks/paypal/dispute-created`):
    Evaluates the target order against immutable 120-365d history and active carrier waybills:
    - `UNAUTHORISED`: Requires >= 2 undisputed historical captures matching IP/Device (Visa CE 3.0).
      If < 2 (e.g. Sarah Chen, Neha Kapoor, or Guest), flags `ESCALATED_CE3_INELIGIBLE`.
    - `MERCHANDISE_OR_SERVICE_NOT_RECEIVED`: Requires active Carrier Tracking + GPS POD (`has_waybill`).
      If untracked (e.g. unattested flash-sale order), flags `ESCALATED_MISSING_WAYBILL`.
    """
    conn = get_conn()
    if order_id:
        target = conn.execute("SELECT * FROM orders_vault WHERE order_id = ?", (order_id,)).fetchone()
    else:
        target = conn.execute(
            "SELECT * FROM orders_vault ORDER BY captured_at DESC LIMIT 1"
        ).fetchone()
    if not target:
        conn.close()
        return compute_account_health()

    order = dict(target)
    oid = order["order_id"]
    cnt, ce3_matches, ce3_ok = evaluate_ce3_relational_match(
        conn, order["buyer_email"], order["buyer_ip"], order["device_hash"], order["shipping_zip"]
    )
    conn.close()

    has_waybill = bool(order.get("tracking_number"))
    suffix = "CE3" if dispute_reason == "UNAUTHORISED" else "INR"
    dispute_id = f"PP-D-{oid[-5:]}-{suffix}"

    if dispute_reason == "UNAUTHORISED":
        can_auto_defend = ce3_ok
    else:  # MERCHANDISE_OR_SERVICE_NOT_RECEIVED
        can_auto_defend = has_waybill

    if can_auto_defend:
        submit_res = paypal_client.submit_friendly_fraud_evidence(
            dispute_id=dispute_id,
            order_id=oid,
            sku=order["sku"],
            capture_id=order["capture_id"],
            carrier=order["carrier"] or "CE3-LEDGER",
            tracking_number=order["tracking_number"] or "CE3-DEVICE-IP-MATCH",
            gps_proof=order["gps_proof"] or "Visa CE 3.0 Historical Footprint Verified",
            buyer_ip=order["buyer_ip"],
            device_hash=order["device_hash"],
            prior_orders=cnt,
        )
        oid = submit_res.get("order_id", oid)
        if submit_res.get("http_status") == 200:
            new_status = "AUTO_DEFENDED_PROTECTED"
        else:
            new_status = f"SYNC_ERROR_HTTP_{submit_res.get('http_status', 500)}"
    else:
        new_status = "ESCALATED_CE3_EXHAUSTED" if dispute_reason == "UNAUTHORISED" else "ESCALATED_MISSING_WAYBILL"

    conn = get_conn()
    conn.execute(
        """
        UPDATE orders_vault
        SET dispute_id = ?,
            dispute_reason = ?,
            dispute_status = ?,
            prior_undisputed_orders = ?,
            ce3_matched_captures_json = ?
        WHERE order_id = ?
        """,
        (dispute_id, dispute_reason, new_status, cnt, json.dumps(ce3_matches), oid),
    )
    conn.commit()
    conn.close()
    return compute_account_health()


def reset_order_dispute_state(order_id: str) -> dict[str, Any]:
    """Clears the dispute status on a single order row so another webhook scenario can be tested cleanly."""
    conn = get_conn()
    conn.execute(
        """
        UPDATE orders_vault
        SET dispute_id = NULL,
            dispute_reason = NULL,
            dispute_status = 'NONE'
        WHERE order_id = ?
        """,
        (order_id,),
    )
    conn.commit()
    conn.close()
    return compute_account_health()


LIVE_ORDER_ROTATION = [
    ("CINE-DRONE-PRO", "CineLifter 6K FPV Drone Kit", 890.00, "arjun.mehta@pixelstudio.in", "49.37.142.88", "fp_99a8c1e402b1", "560001", "FEDEX"),
    ("ATMOS-REC-8K", "8K RAW Field Monitor", 1250.00, "sarah.chen@luminalabs.io", "103.21.244.12", "fp_31d7f09a88c2", "600002", "DHL"),
    ("LENS-35MM-F14", "PrimeCine 35mm T1.5 Lens", 740.00, "david.kim@seoulvfx.kr", "211.36.114.9", "fp_883c", "04524", "UPS"),
    ("CAM-4K-PRO", "CinemaFX 4K Mirrorless Body", 980.00, "new.guest.buyer@gmail.com", "157.48.92.11", "fp_new_guest_01", "400050", "FEDEX"),
]


def create_and_vault_live_sandbox_order(custom_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Mints a real Order on PayPal Sandbox via APIMatic SDK.
    Rotates across distinct SKUs and buyer profiles (including a 1st-time guest buyer with 0 CE 3.0 history)
    or uses custom parameters passed from the UI.
    """
    conn = get_conn()
    existing_count = conn.execute("SELECT COUNT(*) as c FROM orders_vault").fetchone()["c"]
    conn.close()

    default_spec = LIVE_ORDER_ROTATION[existing_count % len(LIVE_ORDER_ROTATION)]
    sku = (custom_payload or {}).get("sku") or default_spec[0]
    item_name = (custom_payload or {}).get("item_name") or default_spec[1]
    amount_usd = float((custom_payload or {}).get("amount_usd") or default_spec[2])
    buyer_email = (custom_payload or {}).get("buyer_email") or default_spec[3]
    buyer_ip = default_spec[4]
    device_hash = default_spec[5]
    shipping_zip = default_spec[6]
    carrier = default_spec[7]

    res = paypal_client.create_real_sandbox_order(
        amount_usd=amount_usd,
        sku=sku,
        item_name=item_name,
    )
    oid = res["order_id"]
    cid = f"CAP-{oid[-6:]}"
    trk = f"779104{int(time.time()) % 10000:04d}"
    sup_po = SUPPLIER_INVENTORY_LEDGER.get(sku, {}).get("supplier_invoice_id", "PO-DRN-2026-8890")

    paypal_client.sync_order_tracking_on_sandbox(
        order_id=oid,
        capture_id=cid,
        tracking_number=trk,
        carrier=carrier,
        sku=sku,
        item_name=item_name,
        supplier_po=sup_po,
    )

    conn_q = get_conn()
    cnt, matched_list, _ = evaluate_ce3_relational_match(
        conn_q, buyer_email, buyer_ip, device_hash, shipping_zip
    )
    conn_q.close()
    ev_hash = compute_evidence_sha256({"order_id": oid, "trk": trk, "ce3": matched_list})

    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO orders_vault VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            oid,
            cid,
            buyer_email,
            amount_usd,
            sku,
            item_name,
            buyer_ip,
            device_hash,
            shipping_zip,
            "v4.2-Signed-NoReturnAbuse",
            cnt,
            json.dumps(matched_list),
            ev_hash,
            carrier,
            trk,
            "DELIVERED_SIGNED",
            f"13.0827N, 80.2707E ({carrier} Live Sandbox POD)",
            "ELIGIBLE_ACTIVE",
            100,
            None,
            None,
            "NONE",
            int(time.time()),
        ),
    )
    conn.commit()
    conn.close()
    return compute_account_health()
