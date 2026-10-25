#!/usr/bin/env bash
# Clone hellohaptik/chatbot_ner at the commit this project was tested against.
#   scripts/fetch_chatbot_ner.sh            # pristine upstream
#   scripts/fetch_chatbot_ner.sh --patched  # plus upstream/0001-*.patch (phone detector fix)
set -euo pipefail
cd "$(dirname "$0")/.."
PIN=6fc5f8bc30b814a3c1cff1718e962ce04e73b772   # master, 2025-02-21
DEST=vendor/chatbot_ner
if [ ! -d "$DEST/.git" ]; then
  git clone -q https://github.com/hellohaptik/chatbot_ner.git "$DEST"
fi
git -C "$DEST" checkout -q "$PIN"
git -C "$DEST" checkout -q -- .
if [ "${1:-}" = "--patched" ]; then
  git -C "$DEST" apply "$PWD"/upstream/0001-*.patch
  echo "chatbot_ner @ ${PIN:0:7} + phone detector patch"
else
  echo "chatbot_ner @ ${PIN:0:7} (pristine)"
fi
