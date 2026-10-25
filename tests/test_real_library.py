"""Tests that call the real hellohaptik/chatbot_ner detectors (vendor/chatbot_ner)."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from chatbot_ner_mcp import engine

ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-10-21T10:00:00+05:30"  # a Wednesday

pytestmark = pytest.mark.skipif(not (engine.chatbot_ner_path() / "ner_v2").is_dir(),
                                reason="run scripts/fetch_chatbot_ner.sh first")


def test_relative_hindi_dates_follow_pinned_clock():
    assert [d["date"] for d in engine.extract_dates("parso aa sakta hu", "hi", now=NOW)] == ["2026-10-23"]
    assert [d["date"] for d in engine.extract_dates("next monday please", now=NOW)] == ["2026-10-26"]


def test_refers_to_past_flips_kal():
    future = engine.extract_dates("kal", "hi", now=NOW)
    past = engine.extract_dates("kal", "hi", refers_to_past=True, now=NOW)
    assert future[0]["date"] == "2026-10-22"
    assert past[0]["date"] == "2026-10-20"


def test_slots_from_one_whatsapp_message():
    out = engine.extract_slots("kal shaam 5 baje aayenge, number 9820012345", language="hi", now=NOW)
    assert [d["date"] for d in out["date"]] == ["2026-10-22"]
    assert [t["time"] for t in out["time"]] == ["17:00"]
    assert [p["e164"] for p in out["phone"]] == ["+919820012345"]


def test_slots_drop_phone_digit_groups_from_numbers():
    out = engine.extract_slots("4 log, mera no 98200 12345", slots=["number", "phone"], language="hi")
    assert [n["value"] for n in out["number"]] == [4]
    assert [p["e164"] for p in out["phone"]] == ["+919820012345"]


def test_indian_number_units():
    assert [n["value"] for n in engine.extract_numbers("budget is 1.5 lakh")] == [150000]
    assert [n["value"] for n in engine.extract_numbers("dedh hazaar", "hi")] == [1500]


def test_unsupported_language_is_refused_not_translated():
    with pytest.raises(ValueError, match="does not support"):
        engine.extract_dates("demain", "fr")


def test_known_upstream_phone_bug_reproduces_on_pristine_checkout():
    # A short number (pincode) before the phone number makes the detector drop it.
    text = "pin 400001 and mobile 9820012345"
    src = engine.chatbot_ner_path() / "ner_v2/detectors/pattern/phone_number/phone_number_detection.py"
    if "self.original_phone_text.append(self.text)" not in src.read_text(encoding="utf-8"):
        pytest.skip("vendor checkout already has the patch applied")
    assert engine.extract_phones(text) == []


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_upstream_patch_fixes_bug_and_keeps_upstream_suite_green(tmp_path):
    copy = tmp_path / "chatbot_ner"
    shutil.copytree(engine.chatbot_ner_path(), copy, ignore=shutil.ignore_patterns("__pycache__"))
    subprocess.run(["git", "-C", str(copy), "checkout", "-q", "--", "."], check=True)
    patch = next((ROOT / "upstream").glob("0001-*.patch"))
    subprocess.run(["git", "-C", str(copy), "apply", str(patch)], check=True)
    env = {**os.environ, "CHATBOT_NER_PATH": str(copy)}

    suite = subprocess.run([sys.executable, str(ROOT / "scripts/upstream_phone_suite.py")],
                           env=env, capture_output=True, text=True)
    assert suite.returncode == 0, suite.stdout + suite.stderr
    assert "22/22 passed" in suite.stdout

    code = ("from chatbot_ner_mcp import engine;"
            "print([p['e164'] for p in engine.extract_phones('pin 400001, call 9820012345 or 9819983132')])")
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "['+919820012345', '+919819983132']"
