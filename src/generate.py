"""
Generation step: runs the RAG SUT against test cases from data/eval_dataset.jsonl
and saves the results to outputs/generations.json for offline evaluation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))


def load_cases() -> list[dict]:
  """Loads evaluation test cases from eval_dataset.jsonl."""
  path = ROOT / "data" / "eval_dataset.jsonl"
  with path.open(encoding="utf-8") as f:
    return [
        json.loads(line)
        for line in f
        if line.strip() and not line.lstrip().startswith("//")
    ]


def main() -> None:
  parser = argparse.ArgumentParser(
      description="Run RAG SUT generation over evaluation dataset."
  )
  parser.add_argument(
      "--n-runs",
      type=int,
      default=1,
      help="Number of evaluation runs per test case",
  )
  args = parser.parse_args()

  from system_under_test import StudentSUT

  sut = StudentSUT()
  records = []

  for case in load_cases():
    for run in range(args.n_runs):
      gen = sut.generate(case)
      records.append({**case, **gen, "run": run})

  out_dir = ROOT / "outputs"
  out_dir.mkdir(exist_ok=True)
  out_path = out_dir / "generations.json"
  out_path.write_text(
      json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
  )
  print(f"Saved {len(records)} records to {out_path}")


if __name__ == "__main__":
  main()