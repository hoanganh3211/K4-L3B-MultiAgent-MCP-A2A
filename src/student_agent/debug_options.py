"""Debug: try different call_tool options."""
from __future__ import annotations

import asyncio
import json
import sys
import os
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

from .config import Settings
from .contracts import Contracts
from .mcp_gateway import connect_gateway


async def main() -> None:
    root = Path(__file__).resolve().parent.parent.parent
    settings = Settings.load(root)
    contracts = Contracts(root / "contracts" / "schemas")

    async with connect_gateway(settings.mcp_endpoint, settings.team_api_key, contracts) as gw:
        session = gw._session

        # Check server capabilities
        print(f"Server capabilities: {session.server_capabilities}")
        print(f"Server info: {session.server_info}")

        # Try with read_timeout
        print("\n=== get_policy with read_timeout=60 ===")
        result = await session.call_tool(
            "get_policy",
            arguments={"case_id": "L3B_CASE_001", "policy_version": "EC_POLICY_V2"},
            read_timeout_seconds=60.0,
        )
        print(f"  is_error: {result.is_error}")
        for block in result.content:
            if hasattr(block, "text"):
                print(f"  text: {block.text}")

        # Try a different case
        print("\n=== get_policy with CASE_050 ===")
        result2 = await session.call_tool(
            "get_policy",
            arguments={"case_id": "L3B_CASE_050", "policy_version": "EC_POLICY_V2"},
            read_timeout_seconds=60.0,
        )
        print(f"  is_error: {result2.is_error}")
        for block in result2.content:
            if hasattr(block, "text"):
                print(f"  text: {block.text}")

        # Try get_order with different formats
        print("\n=== get_order ===")
        result3 = await session.call_tool(
            "get_order",
            arguments={"case_id": "L3B_CASE_001", "order_id": "af0bbb47f125381ce9f3597dc70ef07b"},
            read_timeout_seconds=60.0,
        )
        print(f"  is_error: {result3.is_error}")
        sc = getattr(result3, "structured_content", None)
        print(f"  structured_content: {json.dumps(sc, indent=2) if sc else None}")
        for block in result3.content:
            if hasattr(block, "text"):
                txt = block.text
                print(f"  text ({len(txt)} chars): {txt[:2000]}")


if __name__ == "__main__":
    asyncio.run(main())
