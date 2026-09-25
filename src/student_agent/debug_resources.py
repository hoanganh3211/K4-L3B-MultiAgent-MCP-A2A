"""Debug: check MCP resources and prompts."""
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

        # Check prompts
        print("=== Prompts ===")
        try:
            prompts = await session.list_prompts()
            print(f"  Prompts: {prompts}")
        except Exception as e:
            print(f"  Error: {e}")

        # Check resources
        print("\n=== Resources ===")
        try:
            resources = await session.list_resources()
            print(f"  Resources: {resources}")
        except Exception as e:
            print(f"  Error: {e}")

        # List tools with full details
        print("\n=== Tools (full details) ===")
        response = await session.list_tools()
        for tool in response.tools:
            schema = getattr(tool, "input_schema", {})
            print(f"\n  {tool.name}: {tool.description}")
            print(f"    schema: {json.dumps(schema, indent=4)}")


if __name__ == "__main__":
    asyncio.run(main())
