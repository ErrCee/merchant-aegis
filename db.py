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
        policy_version TEXT NOT NULL,
        prior_undisputed_orders INTEGER NOT NULL,
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
        cur.execute("SELECT COUNT(*) as cnt FROM orders_vault")
        if cur.fetchone()["cnt"] == 0:
            seed_baseline_orders(conn)
    conn.close()


def reset_demo_db() -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM orders_vault")
    cur.execute("DELETE FROM legitimacy_dossiers")
    cur.execute("DELETE FROM api_audit_log")
    conn.commit()
    seed_baseline_orders(conn)
    conn.close()


def seed_baseline_orders(conn: sqlite3.Connection) -> None:
    now = int(time.time())
    baseline_rows = [
        (
            "PP-ORD-8801",
            "CAP-99201A",
            "arjun.mehta@pixelstudio.in",
            800.00,
            "CAM-4K-PRO",
            "CinemaFX 4K Mirrorless Body",
            "49.37.142.88",
            "fp_99a8c1e402b1",
            "v4.2-Signed-NoReturnAbuse",
            3,
            "FEDEX",
            "774920194821",
            "DELIVERED_SIGNED",
            "12.9716N, 77.5946E (Signed: A. Mehta)",
            "ELIGIBLE_ACTIVE",
            100,
            None,
            None,
            "NONE",
            now - 7200,
        ),
        (
            "PP-ORD-8802",
            "CAP-99202B",
            "sarah.chen@luminalabs.io",
            640.00,
            "LENS-35MM-F14",
            "PrimeCine 35mm T1.5 Lens",
            "103.21.244.12",
            "fp_31d7f09a88c2",
            "v4.2-Signed-NoReturnAbuse",
            2,
            "DHL",
            "4491028471",
            "DELIVERED_SIGNED",
            "13.0827N, 80.2707E (Front DeskPOD)",
            "ELIGIBLE_ACTIVE",
            100,
            None,
            None,
            "NONE",
            now - 5400,
        ),
    ]
    conn.executemany(
        """
        INSERT INTO orders_vault VALUES (
            ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
        )
        """,
        baseline_rows,
    )
    conn.commit()


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
