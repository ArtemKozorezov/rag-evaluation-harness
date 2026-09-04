"""
Deterministic functional tests over saved generations (offline, no model).

Reads outputs/generations.json (created by src/generate.py). Fast, free, reproducible.

"""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "eval_dataset.jsonl"
GENERATIONS = ROOT / "outputs" / "generations.json"


def load_cases() -> list[dict]:
    with DATASET.open(encoding="utf-8") as f:
        return [
            json.loads(line)
            for line in f
            if line.strip() and not line.lstrip().startswith("//")
        ]


def load_generations() -> list[dict]:
    if not GENERATIONS.exists():
        pytest.skip("Generate outputs/generations.json first: `python src/generate.py`")
    return json.loads(GENERATIONS.read_text(encoding="utf-8"))


def test_dataset_has_min_cases():
    """Sanity: dataset contains at least 30 cases."""
    cases = load_cases()
    assert len(cases) >= 30, "Add test cases to data/eval_dataset.jsonl"


def test_dataset_schema():
    """Dataset contains required metadata fields."""
    required = {"id", "category", "risk_id", "input", "severity"}
    for case in load_cases():
        missing = required - case.keys()
        assert not missing, f"Case {case.get('id')} is missing fields: {missing}"


def test_generations_have_output():
    """Each saved record contains 'output' (generation step contract)."""
    for rec in load_generations():
        assert "output" in rec, f"Record {rec.get('id')} without 'output'"
