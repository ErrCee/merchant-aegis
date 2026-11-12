import hashlib
import json
import sqlite3
import time
from typing import Any

DB_PATH = "zerohold.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    return conn


def init_db(seed_initial: bool = True) -> None:
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS orders_vault (
        order_id TEXT PRIMARY KEY,
        capture_id TEXT NOT NULL,
        buyer_email TEXT NOT NULL,
        amount_usd REAL NOT NULL,
        sku TEXT NOT NULL,
        item_name TEXT NOT NULL,
        buyer_ip TEXT NOT NULL,
        device_hash TEXT NOT NULL,
        shipping_zip TEXT NOT NULL,
        policy_version TEXT NOT NULL,
        prior_undisputed_orders INTEGER NOT NULL,
        ce3_matched_captures_json TEXT NOT NULL,
        evidence_sha256 TEXT NOT NULL,
        carrier TEXT,
        tracking_number TEXT,
        delivery_status TEXT NOT NULL,
        gps_proof TEXT,
        seller_protection TEXT NOT NULL,
        evidence_readiness_pct INTEGER NOT NULL,
        dispute_id TEXT,
        dispute_reason TEXT,
        dispute_status TEXT NOT NULL,
        captured_at INTEGER NOT NULL
    )
    """)

    # Historical settled captures (120 to 365 days old) for relational Visa CE 3.0 SQL matching
    cur.execute("""
    CREATE TABLE IF NOT EXISTS buyer_history_ledger (
        hist_capture_id TEXT PRIMARY KEY,
        paypal_order_id TEXT NOT NULL,
        buyer_email TEXT NOT NULL,
        amount_usd REAL NOT NULL,
        sku TEXT NOT NULL,
        buyer_ip TEXT NOT NULL,
        device_hash TEXT NOT NULL,
        shipping_zip TEXT NOT NULL,
        settled_days_ago INTEGER NOT NULL,
        was_disputed INTEGER NOT NULL DEFAULT 0
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS legitimacy_dossiers (
        dossier_id TEXT PRIMARY KEY,
        created_at INTEGER NOT NULL,
        freeze_risk_before REAL NOT NULL,
        freeze_risk_after REAL NOT NULL,
        gmv_24h REAL NOT NULL,
        baseline_gmv REAL NOT NULL,
        z_score REAL NOT NULL,
        synced_orders_count INTEGER NOT NULL,
        supplier_po_ref TEXT NOT NULL,
        carrier_manifest_ref TEXT NOT NULL,
        campaign_utm_ref TEXT NOT NULL,
        dispatch_sla_pct REAL NOT NULL,
        dossier_json TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS api_audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts INTEGER NOT NULL,
        engine TEXT NOT NULL,
        sdk_component TEXT NOT NULL,
        endpoint TEXT NOT NULL,
        http_status INTEGER NOT NULL,
        latency_ms REAL NOT NULL,
        summary TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """)

    conn.commit()
    if seed_initial:
        seed_historical_buyer_ledger(conn)
    conn.close()


def seed_historical_buyer_ledger(conn: sqlite3.Connection) -> None:
    """
    Seeds realistic 120-365d buyer history across all personas:
    - Arjun Mehta: 3 undisputed orders -> CE 3.0 Eligible (3/2)
    - Sarah Chen: 1 undisputed order + 1 prior disputed order (240d ago) -> CE 3.0 Ineligible (1/2), but INR Eligible via DHL POD
    - Vikram Rao, David Kim, Lucas Meyer: 2 undisputed orders each -> CE 3.0 Eligible (2/2)
    - Neha Kapoor, Priya Nair: 1 undisputed order each -> CE 3.0 Ineligible (1/2)
    """
    hist_rows = [
        # Persona 1: Arjun Mehta (3 undisputed 120-365d captures -> Passes CE 3.0)
        ("CAP-HIST-4410A", "4H910284A1", "arjun.mehta@pixelstudio.in", 420.00, "CF-CARD-512G", "49.37.142.88", "fp_99a8c1e402b1", "560001", 142, 0),
        ("CAP-HIST-3892B", "9K281940B2", "arjun.mehta@pixelstudio.in", 680.00, "TRIPOD-PRO-X", "49.37.142.88", "fp_99a8c1e402b1", "560001", 210, 0),
        ("CAP-HIST-2104C", "7M109482C3", "arjun.mehta@pixelstudio.in", 310.00, "MIC-SHOTGUN-V2", "49.37.199.04", "fp_99a8c1e402b1", "560001", 295, 0),
        # Persona 2: Sarah Chen (1 undisputed + 1 disputed 240d ago -> Fails CE 3.0 with 1/2, Passes INR via DHL POD)
        ("CAP-HIST-5501D", "2P849102D4", "sarah.chen@luminalabs.io", 540.00, "ND-FILTER-KIT", "103.21.244.12", "fp_31d7f09a88c2", "600002", 155, 0),
        ("CAP-HIST-5190E", "6L392019E5", "sarah.chen@luminalabs.io", 890.00, "MONITOR-5IN", "103.21.244.12", "fp_31d7f09a88c2", "600002", 240, 1),
        # Flash-Sale Buyers: Vikram, David, Lucas (2 undisputed each -> Pass CE 3.0)
        ("CAP-HIST-7001F", "8A102938F1", "vikram.rao@studio9.in", 950.00, "CINE-MATTEBOX", "49.44.19.10", "fp_881a", "400001", 168, 0),
        ("CAP-HIST-7002G", "8B102938G2", "vikram.rao@studio9.in", 1120.00, "FOLLOW-FOCUS-W", "49.44.19.10", "fp_881a", "400001", 230, 0),
        ("CAP-HIST-7003H", "8C102938H3", "david.kim@seoulvfx.kr", 1400.00, "PL-MOUNT-ADAPT", "211.36.114.9", "fp_883c", "04524", 180, 0),
        ("CAP-HIST-7004J", "8D102938J4", "david.kim@seoulvfx.kr", 820.00, "V-MOUNT-BATT-4X", "211.36.114.9", "fp_883c", "04524", 275, 0),
        ("CAP-HIST-7005K", "8E102938K5", "lucas.meyer@berlinpost.de", 760.00, "TIME-CODE-BOX", "84.112.90.14", "fp_885e", "10115", 190, 0),
        ("CAP-HIST-7006L", "8F102938L6", "lucas.meyer@berlinpost.de", 1340.00, "COLOR-PANEL-PRO", "84.112.90.14", "fp_885e", "10115", 310, 0),
        # Flash-Sale Buyers: Neha & Priya (Only 1 prior order -> Fail CE 3.0, require Waybill for INR)
        ("CAP-HIST-8001M", "9A204918M1", "neha.kapoor@cinecraft.co", 620.00, "BATTERY-BELT", "106.51.73.22", "fp_882b", "110001", 175, 0),
        ("CAP-HIST-8002N", "9B204918N2", "priya.nair@keralafilm.in", 480.00, "SDI-CABLE-PRO", "117.192.41.5", "fp_884d", "682001", 205, 0),
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO buyer_history_ledger VALUES (?,?,?,?,?,?,?,?,?,?)",
        hist_rows,
    )
    conn.commit()


def evaluate_ce3_relational_match(
    conn: sqlite3.Connection,
    buyer_email: str,
    buyer_ip: str,
    device_hash: str,
    shipping_zip: str,
) -> tuple[int, list[dict[str, Any]], bool]:
    """
    Queries `buyer_history_ledger` for captures settled 120 to 365 days ago.
    Returns (valid_undisputed_count, all_history_records_with_status, is_ce3_qualified).
    """
    rows = conn.execute(
        """
        SELECT * FROM buyer_history_ledger
        WHERE buyer_email = ?
          AND settled_days_ago BETWEEN 120 AND 365
        ORDER BY settled_days_ago ASC
        """,
        (buyer_email,),
    ).fetchall()

    all_records: list[dict[str, Any]] = []
    valid_count = 0
    for r in rows:
        matched_fields = ["buyer_email"]
        ip_or_device = False
        if r["buyer_ip"] == buyer_ip:
            matched_fields.append("buyer_ip")
            ip_or_device = True
        if r["device_hash"] == device_hash:
            matched_fields.append("device_hash")
            ip_or_device = True
        if r["shipping_zip"] == shipping_zip:
            matched_fields.append("shipping_zip")

        is_disputed = bool(r["was_disputed"])
        qualifies = (not is_disputed) and len(matched_fields) >= 2 and ip_or_device
        if qualifies:
            valid_count += 1

        all_records.append({
            "hist_capture_id": r["hist_capture_id"],
            "paypal_order_id": r["paypal_order_id"],
            "amount_usd": r["amount_usd"],
            "sku": r["sku"],
            "settled_days_ago": r["settled_days_ago"],
            "matched_identifiers": matched_fields,
            "was_disputed": is_disputed,
            "qualifies_for_ce3": qualifies,
        })

    return valid_count, all_records, (valid_count >= 2)


def compute_evidence_sha256(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def reset_demo_db() -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM orders_vault")
    cur.execute("DELETE FROM legitimacy_dossiers")
    cur.execute("DELETE FROM api_audit_log")
    conn.commit()
    seed_historical_buyer_ledger(conn)
    conn.close()


def log_api_call(
    engine: str,
    sdk_component: str,
    endpoint: str,
    http_status: int,
    latency_ms: float,
    summary: str,
    payload: dict[str, Any],
) -> None:
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO api_audit_log (ts, engine, sdk_component, endpoint, http_status, latency_ms, summary, payload_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(time.time()),
            engine,
            sdk_component,
            endpoint,
            http_status,
            round(latency_ms, 1),
            summary,
            json.dumps(payload, indent=2),
        ),
    )
    conn.commit()
    conn.close()
