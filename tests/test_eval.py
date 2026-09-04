"""
Metric evaluation OVER saved generations (offline, deterministic, keyless).

Reads outputs/generations.json and computes metrics WITHOUT model calls:
- Retrieval metrics are computed purely from gold_doc_ids — no model needed;
- DeepEval should be used via BaseMetric (deterministic, no LLM judge);
- Ragas — non-LLM only and ONLY via local try/except (fragile on Colab).

Non-determinism: if generated over multiple runs (--n-runs), evaluate PASS-RATE per run, not a single run.

⚠️ Selection of metrics and thresholds is your evaluated decision (Strategy & DoD).
"""

import json
from collections import defaultdict
from pathlib import Path

import pytest
# Import local model for semantic similarity calculation
from sentence_transformers import SentenceTransformer, util

from src.metrics.custom_metrics import (
    batch_language_compliance_metric,
    batch_safe_refusal_metric,
    batch_mrr_metric,
    batch_faithfulness_metric,
)

ROOT = Path(__file__).resolve().parents[1]
GENERATIONS = ROOT / "outputs" / "generations.json"

# Set pass-rate threshold from strategy (at least 4 out of 5 runs must succeed)
PASS_RATE_THRESHOLD = 0.8  

# Initialize lightweight local model for text comparison (~90 MB)
# Downloads once and computes cosine similarity without API keys
@pytest.fixture(scope="module")
def similarity_model():
    return SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")


def load_generations() -> list[dict]:
    if not GENERATIONS.exists():
        pytest.skip("Generate outputs/generations.json first: `python src/generate.py`")
    return json.loads(GENERATIONS.read_text(encoding="utf-8"))


def pass_rate_by_case(records, predicate) -> dict:
    """Fraction of runs passing `predicate`, calculated per case ID."""
    buckets = defaultdict(list)
    for rec in records:
        buckets[rec["id"]].append(bool(predicate(rec)))
    return {cid: sum(v) / len(v) for cid, v in buckets.items()}


# METRIC 1: Retrieval Hit Rate (Recall@K / Retrieval Quality)

def test_retrieval_hit_rate_meets_threshold():
    """
    Search quality check (R-01): verifies whether gold_doc_ids are present
    in the list of actually retrieved sources without invoking the LLM.
    """
    records = load_generations()
    
    def hit_predicate(rec):
        actual_sources = rec.get("sources", [])
        gold_sources = rec.get("gold_doc_ids", [])
        
        # If this is a negative test (Out-of-Domain), no sources exist in DB by definition
        if not gold_sources:
            return True
            
        # Case succeeds if search engine retrieved at least one expected source
        return any(doc_id in actual_sources for doc_id in gold_sources)

    # Calculate pass-rate for each unique ID (across 5 runs)
    rates = pass_rate_by_case(records, hit_predicate)
    
    # Check if every test case passed the 80% stability threshold
    for cid, rate in rates.items():
        assert rate >= PASS_RATE_THRESHOLD, (
            f"Case {cid} failed search stability threshold. "
            f"Actual pass-rate: {rate:.2f}, expected: {PASS_RATE_THRESHOLD}"
        )


# METRIC 2: Mean Reciprocal Rank (MRR / Search Ranking R-01)

def test_mrr_meets_threshold():
    """
    Search ranking check (R-01): computes aggregated MRR value across the dataset.
    """
    records = load_generations()
    score = batch_mrr_metric(records)
    mrr_threshold = 0.75
    assert score >= mrr_threshold, (
        f"Aggregated MRR score ({score:.2f}) is below threshold {mrr_threshold}"
    )


# METRIC 3: Non-LLM Faithfulness (Output Groundedness without LLM Judge R-02)

def test_faithfulness_non_llm_meets_threshold():
    """
    Output groundedness check in retrieved context (R-02):
    evaluates the fraction of output facts/tokens supported by sources (without LLM judge).
    """
    records = load_generations()
    score = batch_faithfulness_metric(records)
    faithfulness_threshold = 0.80
    assert score >= faithfulness_threshold, (
        f"Faithfulness score ({score:.2f}) is below threshold {faithfulness_threshold}"
    )


# METRIC 4: Semantic Similarity

def test_semantic_similarity_meets_threshold(similarity_model):
    """
    Factual correctness check (R-02 / R-04): compares generated output text
    against expected gold answer using cosine similarity of embeddings.
    """
    records = load_generations()
    
    # Filter for Happy Path and Edge cases where a clear expected answer exists
    eval_records = [
        r for r in records 
        if r.get("category") in ["happy_path", "edge"] and "expected" in r
    ]
    
    if not eval_records:
        pytest.skip("No happy_path/edge category cases found in generated files for semantic evaluation.")

    def similarity_predicate(rec):
        gen_text = rec.get("output", "")
        gold_text = rec.get("expected", "")
        
        if not gen_text or not gold_text:
            return False
            
        # Encode both texts to vectors and compute cosine similarity
        emb1 = similarity_model.encode(gen_text, convert_to_tensor=True)
        emb2 = similarity_model.encode(gold_text, convert_to_tensor=True)
        score = util.cos_sim(emb1, emb2).item()
        
        # Similarity threshold from strategy DoD (allows minor phrasing variations)
        return score >= 0.80  

    # Compute semantic stability pass-rate
    rates = pass_rate_by_case(eval_records, similarity_predicate)
    
    for cid, rate in rates.items():
        assert rate >= PASS_RATE_THRESHOLD, (
            f"Case {cid} has insufficient semantic similarity or unstable generation. "
            f"Pass-rate: {rate:.2f}, required: {PASS_RATE_THRESHOLD}"
        )


# METRIC 5: Language Compliance (Language Drift Control / Risk R-04)

def test_language_compliance_meets_threshold():
    """
    Language compliance check (R-04): verifies whether response language
    matches input query language across all generations.
    """
    records = load_generations()
    score = batch_language_compliance_metric(records)
    
    # Recommended compliance threshold (e.g., 90%)
    compliance_threshold = 0.90
    assert score >= compliance_threshold, (
        f"Overall language compliance score ({score:.2f}) is below threshold {compliance_threshold}"
    )


# METRIC 6: Safe Refusal Strictness (Safe Refusal Quality / Risk R-03)

def test_safe_refusal_strictness_meets_threshold():
    """
    Safe refusal quality check on out-of-domain queries (R-03):
    evaluates refusal quality for Negative categories.
    """
    records = load_generations()
    score = batch_safe_refusal_metric(records)
    
    # Recommended refusal reliability threshold (e.g., 80%)
    refusal_threshold = 0.80
    assert score >= refusal_threshold, (
        f"Safe refusal quality index ({score:.2f}) is below threshold {refusal_threshold}"
    )