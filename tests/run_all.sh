#!/usr/bin/env bash
# One command: python score tests (+ JS/Python agreement), engine mock, static build. Needs: python3, node.
set -e
cd "$(dirname "$0")/.."
python3 tests/test_score.py
python3 tests/test_pipeline.py
node tests/engine_mock.mjs
python3 -m pipeline.build static >/dev/null && echo "ok static build -> docs/"
echo "ALL AUTOMATED CHECKS PASSED. Now do the manual checklist in TESTING.md"
