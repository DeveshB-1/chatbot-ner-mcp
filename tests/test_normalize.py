"""Pure normalizer tests: fed with raw chatbot_ner output shapes, no checkout needed."""
from chatbot_ner_mcp import engine


def test_dates_iso_and_range_roles():
    raw = [
        {"value": {"dd": 28, "mm": 10, "yy": 2026, "type": "date"}, "from": False, "to": False,
         "start_range": True, "end_range": False, "normal": False},
        {"value": {"dd": 2, "mm": 11, "yy": 2026, "type": "date"}, "from": False, "to": False,
         "start_range": False, "end_range": True, "normal": False},
    ]
    out = engine.normalize_dates(raw, ["28 oct to 2", "28 oct to 2"])
    assert [o["date"] for o in out] == ["2026-10-28", "2026-11-02"]
    assert [o["role"] for o in out] == ["start", "end"]


def test_times_to_24h_and_relative():
    raw = [{"hh": 5, "mm": 0, "nn": "pm", "tz": "Asia/Kolkata"},
           {"hh": 12, "mm": 15, "nn": "am", "tz": "Asia/Kolkata"},
           {"hh": 12, "mm": 0, "nn": "pm", "tz": "Asia/Kolkata"},
           {"hh": 2, "mm": 0, "nn": "df", "tz": "Asia/Kolkata"}]
    out = engine.normalize_times(raw, ["5 baje", "12:15 am", "12 pm", "in 2 hours"])
    assert [o.get("time") for o in out[:3]] == ["17:00", "00:15", "12:00"]
    assert out[3] == {"kind": "relative", "hours": 2, "minutes": 0, "text": "in 2 hours"}


def test_numbers_int_and_float():
    out = engine.normalize_numbers([{"value": "150000", "unit": None}, {"value": "2.5", "unit": "kg"}],
                                   ["1.5 lakh", "2.5 kg"])
    assert out[0]["value"] == 150000 and isinstance(out[0]["value"], int)
    assert out[1] == {"value": 2.5, "unit": "kg", "text": "2.5 kg"}


def test_phones_e164():
    out = engine.normalize_phones([{"country_calling_code": "91", "value": "9820012345"}], ["98200 12345"])
    assert out[0]["e164"] == "+919820012345"
