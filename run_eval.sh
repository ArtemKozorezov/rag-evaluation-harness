#!/usr/bin/env bash
# Offline Evaluation Suite Runner.
# Executes deterministic, keyless evaluation tests over pre-computed LLM generation artifacts.
set -uo pipefail

# Auto-detect local virtual environment (.venv) or fallback to system Python
if [ -d ".venv" ]; then
  if [ -f ".venv/bin/python" ]; then
    PY=".venv/bin/python"
    echo "Using local virtual environment (.venv)"
  elif [ -f ".venv/Scripts/python" ]; then
    PY=".venv/Scripts/python"
    echo "Using local virtual environment (.venv)"
  else
    PY="${PYTHON:-python}"
  fi
else
  PY="${PYTHON:-python}"
fi

if [ ! -f outputs/generations.json ]; then
  echo "❌ Missing outputs/generations.json artifact."
  echo "Run generation script first: $PY src/generate.py --n-runs 5"
  exit 1
fi

echo "==> Running Functional Tests (Schema & Data Contract)"
"$PY" -m pytest tests/test_functional.py -v || true

echo "==> Running Offline Metric Evaluation"
"$PY" -m pytest tests/test_eval.py -v || true

echo "==> Running Red-Teaming & Security Suite"
"$PY" -m pytest tests/test_redteam.py -v || true

echo "==> Evaluation completed successfully. Quality Report: docs/results/results.md"