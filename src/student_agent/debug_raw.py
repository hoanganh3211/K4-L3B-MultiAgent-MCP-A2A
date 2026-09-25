"""Debug: raw MCP call to see exact error responses."""
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

        # Try calling get_order with the exact args
        print("=== get_order (valid order) ===")
        result = await session.call_tool("get_order", arguments={
            "case_id": "L3B_CASE_001",
            "order_id": "af0bbb47f125381ce9f3597dc70ef07b",
        })
        print(f"  is_error: {result.is_error}")
        print(f"  content type: {type(result.content)}")
        for block in result.content:
            print(f"  block type: {type(block).__name__}")
            if hasattr(block, "text"):
                print(f"  text: {block.text[:1000]}")
            # Print all attributes
            for attr in dir(block):
                if not attr.startswith("_"):
                    try:
                        val = getattr(block, attr)
                        if not callable(val):
                            print(f"  {attr}: {val}")
                    except:
                        pass
        # Check structured_content
        sc = getattr(result, "structured_content", None)
        print(f"  structured_content: {sc}")

        print("\n=== get_order (fake candidate) ===")
        result2 = await session.call_tool("get_order", arguments={
            "case_id": "L3B_CASE_001",
            "order_id": "candidate-001",
        })
        print(f"  is_error: {result2.is_error}")
        for block in result2.content:
            if hasattr(block, "text"):
                print(f"  text: {block.text[:1000]}")

        print("\n=== get_policy ===")
        result3 = await session.call_tool("get_policy", arguments={
            "case_id": "L3B_CASE_001",
            "policy_version": "EC_POLICY_V2",
        })
        print(f"  is_error: {result3.is_error}")
        for block in result3.content:
            if hasattr(block, "text"):
                print(f"  text: {block.text[:1000]}")
        sc3 = getattr(result3, "structured_content", None)
        print(f"  structured_content: {sc3}")


if __name__ == "__main__":
    asyncio.run(main())
