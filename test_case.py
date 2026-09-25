import asyncio, json
from pathlib import Path
from student_agent.config import Settings
from student_agent.contracts import Contracts
from student_agent.mcp_gateway import connect_gateway
from student_agent.workflow import solve_case
from student_agent.trace import TraceWriter

async def run():
    root = Path(".")
    s = Settings.load(root)
    c = Contracts(root/"contracts"/"schemas")
    trace = TraceWriter(root / "traces" / "test.jsonl", c)
    case = json.loads((root / "inputs" / "L3B_CASE_001.json").read_text(encoding="utf-8"))
    async with connect_gateway(s.mcp_endpoint, s.team_api_key, c) as gw:
        out = await solve_case(case, gw, trace)
        print("EVIDENCE REFS:", len(out.get("evidence_refs", [])))
        print(json.dumps(out, indent=2))

asyncio.run(run())
