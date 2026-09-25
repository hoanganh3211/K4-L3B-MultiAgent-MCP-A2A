"""Debug: list MCP tool schemas (input arguments)."""
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
        response = await gw._session.list_tools()
        for tool in response.tools:
            print(f"\n{'='*60}")
            print(f"Tool: {tool.name}")
            print(f"Description: {tool.description}")
            schema = getattr(tool, "input_schema", None)
            if schema:
                print(f"Input Schema: {json.dumps(schema, indent=2)}")
            else:
                print(f"Input Schema: (none)")
            print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
