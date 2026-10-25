"""Run chatbot_ner's own phone-number YAML suite without Django.

Same assertions as ner_v2/tests/pattern/phone_number/test_phone_number_detection.py,
minus django.test.TestCase, so it runs against any checkout:

    CHATBOT_NER_PATH=vendor/chatbot_ner uv run python scripts/upstream_phone_suite.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from chatbot_ner_mcp import engine  # noqa: E402  (configures logging, sets sys.path)


def main() -> int:
    root = engine.chatbot_ner_path()
    engine._load()
    from ner_v2.detectors.pattern.phone_number.phone_number_detection import PhoneDetector

    suite = root / "ner_v2/tests/pattern/phone_number/phone_number_ner_tests.yaml"
    data = yaml.safe_load(suite.read_text(encoding="utf-8"))
    failed = total = 0
    for language, cases in data["tests"].items():
        for case in cases:
            total += 1
            expected = [({"value": str(o["value"]), "country_calling_code": str(o["country_calling_code"])},
                         o["original_text"].lower().strip())
                        for o in case["outputs"] if o["original_text"]]
            det = PhoneDetector(entity_name="phone_number", language=language, locale=case["locale"])
            phones, spans = det.detect_entity(case["message"])
            got = list(zip(phones, spans))
            ok = len(phones) == len(spans) == len(expected) and all(g in expected for g in got)
            if not ok:
                failed += 1
                print(f"FAIL {case['id']}: {case['message']!r}\n     want {expected}\n     got  {got}")
    print(f"upstream phone suite ({suite.relative_to(root)}): {total - failed}/{total} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
