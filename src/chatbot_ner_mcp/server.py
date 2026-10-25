"""MCP server exposing chatbot_ner detectors as tools for LLM agents.

The split it encourages: the model reads the conversation and decides intent and tense
(is "kal" yesterday or tomorrow here?), and chatbot_ner does the calendar and number
arithmetic, which it does the same way every time.
"""
from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from . import engine

mcp = MCPServer("chatbot-ner")


@mcp.tool()
def extract_dates(text: str, language: str = "en", timezone: str = engine.DEFAULT_TZ,
                  refers_to_past: bool = False, now: str | None = None) -> list[dict]:
    """Resolve dates in a user message to ISO YYYY-MM-DD.

    Handles absolute dates (5th nov, 31/10), relative ones (tomorrow, next monday,
    parso, agle somvar) and ranges (role = start/end). Set refers_to_past=True when the
    user is talking about the past ("I paid kal" means yesterday), since Hindi kal/parso
    point both ways. `language` is the ISO 639-1 code of the message (en, hi, mr, gu,
    bn, ta, te); romanised Hindi (Hinglish) uses hi. `now` (ISO 8601, optional) pins
    the reference clock; default is the server clock."""
    return engine.extract_dates(text, language, timezone, refers_to_past, now)


@mcp.tool()
def extract_times(text: str, language: str = "en", timezone: str = engine.DEFAULT_TZ,
                  now: str | None = None) -> list[dict]:
    """Resolve times of day to 24h HH:MM (kind=clock), e.g. "7.30pm", "shaam 5 baje".
    Offsets like "in 2 hours" come back as kind=relative with hours/minutes."""
    return engine.extract_times(text, language, timezone, now)


@mcp.tool()
def extract_numbers(text: str, language: str = "en") -> list[dict]:
    """Extract numbers, including Indian units and spoken forms: "1.5 lakh" -> 150000,
    "2,50,000" -> 250000, "dedh hazaar" -> 1500, "5k" -> 5000."""
    return engine.extract_numbers(text, language)


@mcp.tool()
def extract_phones(text: str, language: str = "en", locale: str = "en-IN") -> list[dict]:
    """Extract phone numbers as E.164 (+919820012345). `locale` sets the default country."""
    return engine.extract_phones(text, language, locale)


@mcp.tool()
def extract_slots(text: str, slots: list[str] | None = None, language: str = "en",
                  timezone: str = engine.DEFAULT_TZ, refers_to_past: bool = False,
                  now: str | None = None) -> dict:
    """Run several detectors on one message. `slots` is any of date, time, number, phone
    (default: all). Use this to fill a booking or callback form from one WhatsApp message."""
    return engine.extract_slots(text, slots, language, timezone, refers_to_past, now)


@mcp.tool()
def supported_languages() -> dict:
    """Languages each detector supports. Others are refused rather than machine-translated."""
    return engine.supported_languages()


def main() -> None:
    engine._load()  # fail fast, before the client starts talking to us
    mcp.run()


if __name__ == "__main__":
    main()
