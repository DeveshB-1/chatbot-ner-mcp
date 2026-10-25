"""Run WhatsApp-style messages through the real chatbot_ner detectors and score them.

Each case states what a human means by the message (not what the library returns),
so a FAIL is a place where an agent relying on the detector would get a wrong slot.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from . import engine

DEFAULT_CASES = engine.REPO_ROOT / "probes" / "whatsapp.yaml"


def _values(slot: str, results: list[dict]) -> list:
    if slot == "date":
        return [r["date"] for r in results]
    if slot == "time":
        return [r["time"] if r["kind"] == "clock" else f"+{r['hours']}h{r['minutes']:02d}m" for r in results]
    if slot == "number":
        return [r["value"] for r in results]
    return [r["e164"] for r in results]


def run_case(case: dict, now: str) -> dict:
    slot, lang = case["slot"], case.get("lang", "en")
    try:
        got_raw = engine.extract_slots(case["text"], [slot], language=lang,
                                       refers_to_past=case.get("past", False),
                                       now=case.get("now", now))[slot]
        got = _values(slot, got_raw)
        error = None
    except Exception as exc:  # report, keep going
        got, error = [], repr(exc)
    expect = case["expect"]
    # dedupe: chatbot_ner repeats the original text once per range end
    ok = error is None and sorted(set(map(str, got))) == sorted(set(map(str, expect)))
    return {"id": case["id"], "slot": slot, "lang": lang, "text": case["text"],
            "expect": expect, "got": got, "ok": ok, "error": error, "note": case.get("note")}


def run(path: Path) -> tuple[list[dict], str]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    now = data["now"]
    return [run_case(c, now) for c in data["cases"]], now


def _short(vals: list, limit: int = 3) -> str:
    vals = list(dict.fromkeys(map(str, vals)))
    s = ", ".join(vals[:limit])
    return s + (f" (+{len(vals) - limit} more)" if len(vals) > limit else "") if vals else "-"


def render(results: list[dict], now: str) -> str:
    lines = [f"chatbot_ner probe  (clock pinned to {now})", ""]
    for r in results:
        mark = "PASS" if r["ok"] else "FAIL"
        lines.append(f"{mark}  {r['id']:<14} {r['slot']:<6} {r['lang']}  {r['text'][:44]:<44}  "
                     f"want {_short(r['expect'])}  got {_short(r['got'])}")
    lines.append("")
    by_slot: dict[str, list[int]] = {}
    for r in results:
        p = by_slot.setdefault(r["slot"], [0, 0])
        p[0] += r["ok"]
        p[1] += 1
    passed = sum(r["ok"] for r in results)
    lines.append("  ".join(f"{s}: {p}/{t}" for s, (p, t) in by_slot.items())
                 + f"   total: {passed}/{len(results)}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ner-probe", description=__doc__)
    ap.add_argument("cases", nargs="?", type=Path, default=DEFAULT_CASES)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--strict", action="store_true", help="exit 1 if any case fails (for CI)")
    args = ap.parse_args(argv)
    results, now = run(args.cases)
    print(json.dumps(results, indent=2, ensure_ascii=False) if args.json else render(results, now))
    return 1 if args.strict and not all(r["ok"] for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
