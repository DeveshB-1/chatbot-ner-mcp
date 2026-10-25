"""Spawn the MCP server over stdio, as Claude Desktop or any MCP client would, and fill a
booking form from one WhatsApp message."""
import json
import sys

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

MSG = "agle hafte nahi, parso shaam 7:30 baje 4 log, budget dedh hazaar per head. mera no 98200 12345"


async def main() -> None:
    params = StdioServerParameters(command=sys.executable, args=["-m", "chatbot_ner_mcp.server"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            print("tools:", ", ".join(t.name for t in (await s.list_tools()).tools))
            print("message:", MSG)
            res = await s.call_tool("extract_slots", {"text": MSG, "language": "hi",
                                                      "now": "2026-10-21T10:00:00+05:30"})
            print(json.dumps(json.loads(res.content[0].text), indent=2, ensure_ascii=False))


anyio.run(main)
