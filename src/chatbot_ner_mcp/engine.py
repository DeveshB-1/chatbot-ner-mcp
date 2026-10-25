"""Thin wrapper over hellohaptik/chatbot_ner's ner_v2 detectors.

Loads the real library from a local checkout (CHATBOT_NER_PATH, or ./vendor/chatbot_ner),
calls its detectors in-process (no Django server, no Elasticsearch), and turns the raw
output into flat, agent-friendly values: ISO dates, 24h times, numbers, E.164 phones.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Iterator

import structlog

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TZ = "Asia/Kolkata"
SLOT_KINDS = ("date", "time", "number", "phone")


def _configure_logging() -> None:
    # chatbot_ner logs through structlog, whose default printer writes to stdout.
    # On an MCP stdio server stdout is the JSON-RPC channel, so one debug line there
    # corrupts the stream. Send everything to stderr and keep only warnings and up.
    level = getattr(logging, os.environ.get("NER_LOG_LEVEL", "ERROR").upper(), logging.ERROR)
    structlog.configure(
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=False,
    )


def chatbot_ner_path() -> Path:
    return Path(os.environ.get("CHATBOT_NER_PATH", REPO_ROOT / "vendor" / "chatbot_ner")).resolve()


_detectors: dict[str, Any] | None = None


def _load() -> dict[str, Any]:
    global _detectors
    if _detectors is not None:
        return _detectors
    path = chatbot_ner_path()
    if not (path / "ner_v2").is_dir():
        raise RuntimeError(
            f"chatbot_ner checkout not found at {path}. Run scripts/fetch_chatbot_ner.sh "
            "or set CHATBOT_NER_PATH."
        )
    _configure_logging()
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
    from ner_v2.detectors.numeral.number.number_detection import NumberDetector
    from ner_v2.detectors.pattern.phone_number.phone_number_detection import PhoneDetector
    from ner_v2.detectors.temporal.date.date_detection import DateAdvancedDetector
    from ner_v2.detectors.temporal.time.time_detection import TimeDetector

    _detectors = {
        "date": DateAdvancedDetector,
        "time": TimeDetector,
        "number": NumberDetector,
        "phone": PhoneDetector,
    }
    return _detectors


@contextlib.contextmanager
def _clock(now: str | None) -> Iterator[None]:
    """Pin the detectors' clock. Relative dates ("parso", "next monday") resolve against it."""
    if not now:
        yield
        return
    from freezegun import freeze_time

    with freeze_time(dt.datetime.fromisoformat(now)):
        yield


def supported_languages() -> dict[str, list[str]]:
    d = _load()
    out = {}
    for kind, cls in d.items():
        if kind == "date":
            inst = cls(entity_name="date", language="en", timezone=DEFAULT_TZ)
        elif kind == "time":
            inst = cls(entity_name="time", language="en", timezone=DEFAULT_TZ)
        else:
            inst = cls(entity_name=kind, language="en")
        out[kind] = sorted(inst.supported_languages)
    return out


def _check_lang(kind: str, language: str) -> None:
    langs = supported_languages()[kind]
    if language not in langs:
        # Unsupported languages make chatbot_ner fall back to Google Translate,
        # which needs a key and a network call. Refuse instead of guessing.
        raise ValueError(f"{kind} detection does not support language {language!r}; supported: {langs}")


# ---------------------------------------------------------------- normalizers (pure)

def normalize_dates(raw: list[dict], originals: list[str]) -> list[dict]:
    out = []
    for item, text in zip(raw, originals):
        v = item["value"]
        role = None
        for key, name in (("start_range", "start"), ("end_range", "end"), ("from", "from"), ("to", "to")):
            if item.get(key):
                role = name
                break
        out.append({
            "date": f"{int(v['yy']):04d}-{int(v['mm']):02d}-{int(v['dd']):02d}",
            "type": v.get("type"),
            "role": role,
            "text": text,
        })
    return out


def normalize_times(raw: list[dict], originals: list[str]) -> list[dict]:
    out = []
    for item, text in zip(raw, originals):
        hh, mm, nn = int(item["hh"]), int(item.get("mm") or 0), item.get("nn")
        if nn == "df":
            # "in 2 hours": an offset from now, not a clock time
            out.append({"kind": "relative", "hours": hh, "minutes": mm, "text": text})
            continue
        if nn == "pm" and hh < 12:
            hh += 12
        elif nn == "am" and hh == 12:
            hh = 0
        out.append({"kind": "clock", "time": f"{hh:02d}:{mm:02d}", "tz": item.get("tz"), "text": text})
    return out


def normalize_numbers(raw: list[dict], originals: list[str]) -> list[dict]:
    out = []
    for item, text in zip(raw, originals):
        s = str(item["value"])
        num: int | float = float(s) if "." in s else int(s)
        out.append({"value": num, "unit": item.get("unit"), "text": text})
    return out


def normalize_phones(raw: list[dict], originals: list[str]) -> list[dict]:
    out = []
    for item, text in zip(raw, originals):
        cc, national = str(item["country_calling_code"]), str(item["value"])
        out.append({"e164": f"+{cc}{national}", "country_calling_code": cc, "national": national, "text": text})
    return out


# ---------------------------------------------------------------- detectors

def extract_dates(text: str, language: str = "en", timezone: str = DEFAULT_TZ,
                  refers_to_past: bool = False, now: str | None = None) -> list[dict]:
    _check_lang("date", language)
    cls = _load()["date"]
    with _clock(now):
        det = cls(entity_name="date", language=language, timezone=timezone,
                  past_date_referenced=refers_to_past)
        raw, originals = det.detect_entity(text)
    return normalize_dates(raw, originals)


def extract_times(text: str, language: str = "en", timezone: str = DEFAULT_TZ,
                  now: str | None = None) -> list[dict]:
    _check_lang("time", language)
    cls = _load()["time"]
    with _clock(now):
        det = cls(entity_name="time", language=language, timezone=timezone)
        raw, originals = det.detect_entity(text)
    return normalize_times(raw, originals)


def extract_numbers(text: str, language: str = "en") -> list[dict]:
    _check_lang("number", language)
    det = _load()["number"](entity_name="number", language=language)
    raw, originals = det.detect_entity(text)
    return normalize_numbers(raw, originals)


def extract_phones(text: str, language: str = "en", locale: str = "en-IN") -> list[dict]:
    _check_lang("phone", language)
    det = _load()["phone"](entity_name="phone", language=language, locale=locale)
    raw, originals = det.detect_entity(text)
    return normalize_phones(raw, originals)


def extract_slots(text: str, slots: list[str] | None = None, language: str = "en",
                  timezone: str = DEFAULT_TZ, refers_to_past: bool = False,
                  now: str | None = None) -> dict[str, list[dict]]:
    slots = list(slots or SLOT_KINDS)
    bad = [s for s in slots if s not in SLOT_KINDS]
    if bad:
        raise ValueError(f"unknown slot kinds {bad}; choose from {list(SLOT_KINDS)}")
    out: dict[str, list[dict]] = {}
    for s in slots:
        if s == "date":
            out[s] = extract_dates(text, language, timezone, refers_to_past, now)
        elif s == "time":
            out[s] = extract_times(text, language, timezone, now)
        elif s == "number":
            out[s] = extract_numbers(text, language)
        else:
            out[s] = extract_phones(text, language)
    if "number" in out and out.get("phone"):
        # The number detector also returns the digit groups of a phone number
        # ("98200", "12345"). Drop those so the agent doesn't read them as quantities.
        phone_parts = set()
        for p in out["phone"]:
            phone_parts.add(p["text"].strip())
            phone_parts.update(g for g in re.split(r"[\s\-().+]+", p["text"]) if g)
        out["number"] = [n for n in out["number"] if n["text"].strip() not in phone_parts]
    return out
