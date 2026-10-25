# chatbot-ner-mcp

An MCP server that lets an LLM agent call Haptik's open-source [chatbot_ner](https://github.com/hellohaptik/chatbot_ner) detectors as tools: dates, times, numbers and phone numbers from WhatsApp-style messages in English, Hinglish and Indic scripts.

Plus a probe suite that runs 36 real-world messages through the library, and a patch for a phone-detector bug the probe found.

## Why this matters to Haptik

Haptik builds LLM agents that book, deliver and call back over WhatsApp. LLMs are shaky at calendar arithmetic ("parso" on a Wednesday, "agle somvar") and at Indian number words ("dedh hazaar", "1.5 lakh"). And they don't give the same answer twice.

chatbot_ner already does this deterministically, in 7 languages, and it's Haptik's own code. This wraps it so the work splits cleanly:

- the model reads the conversation and decides intent and tense (is "kal" yesterday or tomorrow here?)
- chatbot_ner does the arithmetic and returns ISO dates, 24h times, plain numbers and E.164 phones

Everything runs in-process against the real library. No Django server, no Elasticsearch, no API keys.

## Tools

| Tool | Returns |
|---|---|
| `extract_dates(text, language, timezone, refers_to_past, now)` | `[{date: "2026-10-23", type, role: start/end/from/to, text}]` |
| `extract_times(text, language, timezone, now)` | `[{kind: "clock", time: "19:30", tz, text}]` or `{kind: "relative", hours, minutes}` for "in 2 hours" |
| `extract_numbers(text, language)` | `[{value: 150000, unit, text}]` |
| `extract_phones(text, language, locale)` | `[{e164: "+919820012345", country_calling_code, national, text}]` |
| `extract_slots(text, slots, ...)` | all of the above from one message; drops the phone's digit groups from `number` so "98200 12345" isn't read as two quantities |
| `supported_languages()` | languages per detector |

Design choices worth knowing:

- `refers_to_past` is a tool argument on purpose. Hindi "kal" and "parso" point both ways, and the model is the one that knows the tense.
- `now` pins the reference clock, so a conversation can be replayed and tested.
- Languages a detector doesn't support are refused. chatbot_ner would otherwise fall back to Google Translate, which needs a key and a network call.
- chatbot_ner logs through structlog, which prints to stdout by default. On an MCP stdio server stdout is the JSON-RPC channel, so one debug line breaks the client. The server routes all of it to stderr (`tests/test_mcp_server.py` runs at DEBUG level to prove it).

## Quickstart

```bash
scripts/fetch_chatbot_ner.sh          # clones hellohaptik/chatbot_ner @ 6fc5f8b into vendor/
uv sync
uv run pytest -q                      # 13 tests, against the real library
uv run ner-probe                      # the 36-message probe
uv run python scripts/demo_mcp_session.py
```

Claude Desktop / any MCP client:

```json
{
  "mcpServers": {
    "chatbot-ner": {
      "command": "uv",
      "args": ["--directory", "/path/to/chatbot-ner-mcp", "run", "chatbot-ner-mcp"]
    }
  }
}
```

## Demo: one WhatsApp message to a booking form (MCP over stdio)

```
$ uv run python scripts/demo_mcp_session.py
tools: extract_dates, extract_times, extract_numbers, extract_phones, extract_slots, supported_languages
message: agle hafte nahi, parso shaam 7:30 baje 4 log, budget dedh hazaar per head. mera no 98200 12345
{
  "date": [
    {
      "date": "2026-10-23",
      "type": "date",
      "role": null,
      "text": "parso"
    }
  ],
  "time": [
    {
      "kind": "clock",
      "time": "19:30",
      "tz": "Asia/Kolkata",
      "text": "7:30"
    }
  ],
  "number": [
    {
      "value": 4,
      "unit": null,
      "text": "4"
    },
    {
      "value": 1500,
      "unit": null,
      "text": "dedh hazaar"
    }
  ],
  "phone": [
    {
      "e164": "+919820012345",
      "country_calling_code": "91",
      "national": "9820012345",
      "text": "98200 12345"
    }
  ]
}
```

Clock pinned to Wednesday 2026-10-21. "parso" resolves to Friday the 23rd, "shaam 7:30" to 19:30, "dedh hazaar" to 1500, and the phone comes back in E.164.

## Probe: 36 messages against the real detectors

`probes/whatsapp.yaml` states what the customer means, not what the library returns. A FAIL is a place where an agent trusting the detector would fill a wrong slot.

```
$ uv run ner-probe
chatbot_ner probe  (clock pinned to 2026-10-21T10:00:00+05:30)

PASS  date-abs-1     date   en  can I get a slot on 5th nov                   want 2026-11-05  got 2026-11-05
PASS  date-abs-2     date   en  31/10 please                                  want 2026-10-31  got 2026-10-31
PASS  date-rel-1     date   en  tomorrow evening works                        want 2026-10-22  got 2026-10-22
PASS  date-rel-2     date   en  day after tomorrow                            want 2026-10-23  got 2026-10-23
PASS  date-rel-3     date   en  next monday please                            want 2026-10-26  got 2026-10-26
PASS  date-day-1     date   en  book for 29th                                 want 2026-10-29  got 2026-10-29
PASS  date-range-1   date   en  from 28 oct to 2 nov                          want 2026-10-28, 2026-11-02  got 2026-10-28, 2026-11-02
FAIL  date-wkend-1   date   en  can someone come this weekend                 want 2026-10-24, 2026-10-25  got 2026-10-24, 2026-10-25, 2026-10-31 (+11 more)
PASS  date-hi-1      date   hi  parso aa sakta hu                             want 2026-10-23  got 2026-10-23
FAIL  date-hi-2      date   hi  agle somvar ko delivery chahiye               want 2026-10-26  got 2026-11-02
PASS  date-hi-3      date   hi  कल शाम को कॉल करना                            want 2026-10-22  got 2026-10-22
PASS  date-hi-past   date   hi  maine kal payment kiya tha                    want 2026-10-20  got 2026-10-20
FAIL  date-mr-1      date   mr  उद्या येऊ शकता का                             want 2026-10-22  got -
PASS  time-en-1      time   en  at 7:30 pm                                    want 19:30  got 19:30
FAIL  time-en-2      time   en  noon is fine                                  want 12:00  got -
FAIL  time-en-3      time   en  between 3 and 5 pm                            want 15:00, 17:00  got 17:00
PASS  time-hi-1      time   hi  shaam 5 baje                                  want 17:00  got 17:00
PASS  time-hi-2      time   hi  subah 10 baje                                 want 10:00  got 10:00
PASS  time-hi-3      time   hi  raat 9:30 baje                                want 21:30  got 21:30
PASS  time-hi-4      time   hi  शाम 6 बजे                                     want 18:00  got 18:00
FAIL  time-hi-5      time   hi  shaam 5 baje 2 log aayenge                    want 17:00  got 17:02
PASS  num-en-1       number en  I need 2 rooms                                want 2  got 2
PASS  num-en-2       number en  budget is 1.5 lakh                            want 150000  got 150000
PASS  num-en-3       number en  2,50,000 rupees                               want 250000  got 250000
PASS  num-en-4       number en  around 5k                                     want 5000  got 5000
PASS  num-hi-1       number hi  dedh hazaar                                   want 1500  got 1500
PASS  num-hi-2       number hi  dhai sau                                      want 250  got 250
FAIL  num-hi-3       number hi  sava do sau                                   want 225  got 200
PASS  ph-1           phone  en  my no is 9820012345                           want +919820012345  got +919820012345
PASS  ph-2           phone  en  +91-98200-12345                               want +919820012345  got +919820012345
PASS  ph-3           phone  en  09820012345                                   want +919820012345  got +919820012345
PASS  ph-4           phone  en  office 022-2345 6789                          want +912223456789  got +912223456789
FAIL  ph-short-1     phone  en  pin 400001 and mobile 9820012345              want +919820012345  got -
FAIL  ph-short-2     phone  en  pin 400001, call 9820012345 or 9819983132     want +919820012345, +919819983132  got +919819983132
PASS  ph-short-3     phone  en  mobile 9820012345, pin 400001                 want +919820012345  got +919820012345
FAIL  ph-long-1      phone  en  order id 9820012345678 is wrong               want -  got +919820012345678

date: 10/13  time: 5/8  number: 6/7  phone: 5/8   total: 26/36
```

What the failures say:

| Case | What happens | Why it matters |
|---|---|---|
| `ph-short-1`, `ph-short-2` | any 6-7 digit number (a pincode, an order id) before the phone number makes the detector drop it, or return a different number with the wrong span | **bug, patched below** |
| `ph-long-1` | a 13-digit order id comes back as an Indian phone number | false positive; Indian mobiles are 10 digits |
| `time-hi-5` | "5 baje 2 log" (5 o'clock, 2 people) reads as 17:02 | the headcount leaks into the minutes |
| `date-hi-2` | "agle somvar" on a Wednesday gives the Monday after next; English "next monday" gives the 26th | Hindi and English disagree on the same phrase |
| `date-wkend-1` | "this weekend" returns 15 dates across 2 months | an agent has to cut the list itself |
| `date-mr-1` | Marathi "उद्या" (tomorrow) isn't detected | `mr` is listed as supported for dates |
| `time-en-2`, `time-en-3`, `num-hi-3` | "noon", "between 3 and 5 pm", "sava do sau" (225) | gaps, not crashes |

Use `--strict` in CI to fail the build on any FAIL, and `--json` for machine output.

## The upstream bug and patch

`ner_v2/detectors/pattern/phone_number/phone_number_detection.py`, from commit `111f8fe` (2024-10-04, "check its length is below 8 ... and exclude them"):

```python
if national_number_len < 8:
    self.original_phone_text.append(self.text)   # appends the whole message, no matching phone
    continue
```

`self.phone` and `self.original_phone_text` are zipped together in `check_for_alphas()`. Appending to one list and not the other shifts every later pair by one. The whole-message "span" never passes the `\W...\W` check, so the first real phone is dropped, and each one after it is paired with the previous one's text:

```
'pin 400001, call 9820012345 or 9819983132'
want [('9820012345', '9820012345'), ('9819983132', '9819983132')]
got  [('9819983132', '9820012345')]          # one phone lost, the other mislabelled
```

The fix is to skip the short match entirely. [`upstream/0001-phone-detector-short-number-misalignment.patch`](upstream/0001-phone-detector-short-number-misalignment.patch) removes that line and adds 3 cases (`en_16`-`en_18`) to chatbot_ner's own `phone_number_ner_tests.yaml`.

Upstream's suite has no CI here and needs Django, so `scripts/upstream_phone_suite.py` runs the same YAML with the same assertions:

```
pristine code + new cases : 20/22 passed   (en_16, en_17 fail)
patched                   : 22/22 passed
probe phone cases         : 5/8 -> 7/8
```

`tests/test_real_library.py` applies the patch to a temp copy and checks both of those on every run. To use the patched detector: `scripts/fetch_chatbot_ner.sh --patched`.

## Limits

- Tested against chatbot_ner @ `6fc5f8b` (master, 2025-02-21) on Python 3.11. Upstream pins Python-3.7-era pandas/numpy; this uses current pandas and the same `phonenumberslite==8.10.18`. Upstream's own phone suite passes 19/19 on this setup.
- Text entities (city, restaurant, etc.) need Elasticsearch and aren't exposed.
- I don't know which chatbot_ner version runs in Haptik production today, so the bug may already be fixed internally.

## Layout

```
src/chatbot_ner_mcp/engine.py   loads chatbot_ner, normalizes output
src/chatbot_ner_mcp/server.py   MCP server (official mcp SDK, stdio)
src/chatbot_ner_mcp/probe.py    ner-probe CLI
probes/whatsapp.yaml            36 cases
upstream/                       patch for hellohaptik/chatbot_ner
scripts/                        fetch, upstream suite runner, MCP demo
tests/                          normalizers, real library, MCP stdio round trip
```
