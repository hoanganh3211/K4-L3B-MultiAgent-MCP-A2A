import asyncio
from pathlib import Path
from student_agent.config import Settings
from student_agent.contracts import Contracts
from student_agent.mcp_gateway import connect_gateway

async def run():
    root = Path(".")
    s = Settings.load(root)
    c = Contracts(root/"contracts"/"schemas")
    async with connect_gateway(s.mcp_endpoint, s.team_api_key, c) as gw:
        print("Calling get_order for case L3B_CASE_001")
        res = await gw._session.call_tool("get_order", arguments={"case_id":"L3B_CASE_001", "order_id":"af0bbb47f125381ce9f3597dc70ef07b"})
        print("get_order ERROR:", res.is_error)
        
        print("Calling get_order for case L3B_CASE_050")
        res2 = await gw._session.call_tool("get_order", arguments={"case_id":"L3B_CASE_050", "order_id":"b30526e0e945e4ab533c623910c22616"})
        print("get_order 50 ERROR:", res2.is_error)

asyncio.run(run())
