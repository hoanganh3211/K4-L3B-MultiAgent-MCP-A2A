"""One-shot debug script: run CASE_001 only and print evidence details."""
from __future__ import annotations

import asyncio
import json
import sys
import os
import traceback
from pathlib import Path

# Force UTF-8 output on Windows
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Make sure .env is loaded before anything else
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

from .config import Settings
from .contracts import Contracts
from .mcp_gateway import connect_gateway, EvidenceGateway


async def _debug_call(
    gateway: EvidenceGateway,
    tool_name: str,
    case_id: str,
    **kwargs: str,
) -> dict | None:
    """Call a single MCP tool with full error logging."""
    print(f"\n{'='*60}")
    print(f"  Calling: {tool_name}")
    print(f"  Args: case_id={case_id}, {kwargs}")
    print(f"{'='*60}")
    try:
        result = await gateway.call(tool_name, case_id=case_id, **kwargs)
        print(f"  [OK] SUCCESS")
        print(f"  evidence_ref: {result.get('evidence_ref')}")
        print(f"  domain: {result.get('domain')}")
        data = result.get("data")
        if data:
            data_str = json.dumps(data, ensure_ascii=False, indent=2)
            if len(data_str) > 800:
                data_str = data_str[:800] + "\n  ... (truncated)"
            print(f"  data: {data_str}")
        warnings = result.get("warnings", [])
        if warnings:
            print(f"  [WARN] warnings: {warnings}")
        return result
    except Exception as exc:
        print(f"  [FAIL] {type(exc).__name__}: {exc}")
        traceback.print_exc()
        return None


async def main() -> None:
    root = Path(__file__).resolve().parent.parent.parent
    settings = Settings.load(root)
    contracts = Contracts(root / "contracts" / "schemas")

    # Load case 001
    case_path = root / "inputs" / "L3B_CASE_001.json"
    case = json.loads(case_path.read_text(encoding="utf-8"))
    case_id = case["case_id"]
    claimed_order = case["customer_request"].get("claimed_order_id", "")
    candidates = case.get("candidate_order_ids", [])
    customer_hint = case.get("customer_unique_id_hint", "")
    policy_ver = case.get("policy_version", "EC_POLICY_V2")

    print(f"\n[DEBUG] Debugging {case_id}")
    print(f"  claimed_order: {claimed_order}")
    print(f"  candidates: {candidates}")
    print(f"  customer_hint: {customer_hint}")
    print(f"  policy_version: {policy_ver}")

    async with connect_gateway(settings.mcp_endpoint, settings.team_api_key, contracts) as gw:
        tools = await gw.list_tools()
        print(f"\n[TOOLS] Available tools: {tools}")

        # 1) Entity: get_order for each candidate
        for oid in candidates:
            await _debug_call(gw, "get_order", case_id, order_id=oid)

        # 2) Customer history
        if customer_hint:
            await _debug_call(gw, "get_customer_history", case_id, customer_unique_id=customer_hint)

        # 3) Shipment
        if claimed_order:
            await _debug_call(gw, "get_shipment_summary", case_id, order_id=claimed_order)

        # 4) Payment
        if claimed_order:
            await _debug_call(gw, "get_order_payments", case_id, order_id=claimed_order)
            await _debug_call(gw, "get_payment_timeline", case_id, order_id=claimed_order)
            await _debug_call(gw, "get_refund_timeline", case_id, order_id=claimed_order)

        # 5) Product
        if claimed_order:
            await _debug_call(gw, "get_product_context", case_id, order_id=claimed_order)
            await _debug_call(gw, "get_order_items", case_id, order_id=claimed_order)

        # 6) Policy
        await _debug_call(gw, "get_policy", case_id, policy_version=policy_ver)

        # 7) Sellers
        if claimed_order:
            await _debug_call(gw, "get_sellers", case_id, order_id=claimed_order)


if __name__ == "__main__":
    asyncio.run(main())
