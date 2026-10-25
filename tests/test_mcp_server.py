"""End to end over MCP stdio: spawn the server, list tools, call one.

Also guards the stdout problem: chatbot_ner's structlog output would corrupt the
JSON-RPC stream if it reached stdout, and the client would fail to parse.
"""
import json
import sys

import anyio
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from chatbot_ner_mcp import engine

pytestmark = pytest.mark.skipif(not (engine.chatbot_ner_path() / "ner_v2").is_dir(),
                                reason="run scripts/fetch_chatbot_ner.sh first")


async def _session_roundtrip():
    params = StdioServerParameters(command=sys.executable, args=["-m", "chatbot_ner_mcp.server"],
                                   env={"NER_LOG_LEVEL": "DEBUG"})  # loudest logging on purpose
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = {t.name for t in (await session.list_tools()).tools}
            res = await session.call_tool("extract_slots", {
                "text": "raat 9:30 baje, budget dedh hazaar", "slots": ["time", "number"],
                "language": "hi", "now": "2026-10-21T10:00:00+05:30"})
            return tools, json.loads(res.content[0].text)


def test_tools_listed_and_callable_over_stdio():
    tools, payload = anyio.run(_session_roundtrip)
    assert {"extract_dates", "extract_times", "extract_numbers", "extract_phones",
            "extract_slots", "supported_languages"} <= tools
    assert [t["time"] for t in payload["time"]] == ["21:30"]
    assert 1500 in [n["value"] for n in payload["number"]]
