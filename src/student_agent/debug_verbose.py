"""Debug: try a single raw MCP call with logging."""
from __future__ import annotations

import asyncio
import json
import sys
import os
import logging
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Enable all MCP/httpx2 logging
logging.basicConfig(level=logging.DEBUG, stream=sys.stdout, force=True)

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

        # Try a single call - get_policy (simplest, no order_id needed)
        print("\n\n=== CALLING get_policy ===")
        result = await session.call_tool("get_policy", arguments={
            "case_id": "L3B_CASE_001",
            "policy_version": "EC_POLICY_V2",
        })
        
        print(f"\nis_error: {result.is_error}")
        print(f"result_type: {getattr(result, 'result_type', 'N/A')}")
        print(f"structured_content: {getattr(result, 'structured_content', None)}")
        print(f"meta: {getattr(result, 'meta', None)}")
        print(f"content count: {len(result.content)}")
        
        for i, block in enumerate(result.content):
            print(f"\n  content[{i}] type: {type(block).__name__}")
            # Dump all fields
            if hasattr(block, 'model_dump'):
                print(f"  content[{i}] dump: {block.model_dump()}")
            elif hasattr(block, 'text'):
                print(f"  content[{i}] text: {block.text}")

        # Also dump full result
        if hasattr(result, 'model_dump'):
            full = result.model_dump()
            # Remove content to keep it short
            print(f"\nFull result (no content): { {k: v for k, v in full.items() if k != 'content'} }")


if __name__ == "__main__":
    asyncio.run(main())
