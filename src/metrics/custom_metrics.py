"""
Custom metrics for the RAG assistant's business risks (Acme Cloud / Track B).
Implements metrics for assessing risks R-01, R-02, R-03, and R-04 based on the test strategy.
"""

from __future__ import annotations
import re

# Acme Cloud corpus for offline faithfulness evaluation (without LLM)
_CORPUS_TEXTS = {
    "d1": "The Acme Cloud Free plan includes 5 GB of storage and one project.",
    "d2": "The Acme Cloud Free plan includes 2 GB of storage.",
    "d3": "The Acme Cloud Pro plan costs 20 US dollars per month and includes 100 GB of storage. Billing is monthly and can be cancelled at any time from the dashboard.",
    "d4": "Acme Cloud Pro Plus is a separate, higher tier that costs 40 US dollars per month.",
    "d5": "You can contact Acme Cloud support at support@acme.example.",
    "d6": "Acme Cloud stores customer data in EU regions only and is GDPR compliant.",
    "d7": "Безкоштовний тариф Acme Cloud надає 5 ГБ сховища та один проєкт.",
    "d8": "Тариф Pro коштує 20 доларів США на місяць.",
}

_STOP_WORDS = {
    "the", "a", "an", "is", "are", "costs", "includes", "and", "of", "in", "to", "at", "be", "can", "per", "you",
    "та", "і", "в", "на", "з", "для", "по", "що", "це", "є", "не", "за", "один", "одна", "одне"
}


# METRIC 1: Mean Reciprocal Rank (MRR / Search / Risk R-01)

def compute_reciprocal_rank(actual_sources: list[str], gold_sources: list[str]) -> float:
    """
    Calculates Reciprocal Rank (RR) for a single record.
    Returns 1 / rank of the first found gold document from gold_sources in the actual_sources list.
    If no document from gold_sources is found, returns 0.0.
    If gold_sources is empty (Out-of-Domain), returns 1.0.
    """
    if not gold_sources:
        return 1.0
    for idx, doc_id in enumerate(actual_sources, start=1):
        if doc_id in gold_sources:
            return 1.0 / idx
    return 0.0


def batch_mrr_metric(records: list[dict]) -> float:
    """Calculates aggregated Mean Reciprocal Rank (MRR) for the entire dataset."""
    if not records:
        return 1.0
    rrs = [compute_reciprocal_rank(r.get("sources", []), r.get("gold_doc_ids", [])) for r in records]
    return sum(rrs) / len(rrs)


# METRIC 2: Non-LLM Faithfulness (Grounding without LLM-as-judge / Risk R-02)

def compute_non_llm_faithfulness(output_text: str, source_ids: list[str], category: str = "") -> float:
    """
    Evaluates output faithfulness relative to retrieved source context without using an LLM-as-judge.
    
    - Returns 1.0 if all facts in the response are supported by retrieved documents or if it is a negative refusal.
    - Penalizes the presence of tokens/numbers in the response that are not present in the retrieved sources.
    """
    if not output_text or category == "negative":
        return 1.0
        
    context_text = " ".join(_CORPUS_TEXTS.get(sid, "") for sid in source_ids).lower()
    
    output_tokens = re.findall(r'\w+', output_text.lower())
    key_tokens = [t for t in output_tokens if t not in _STOP_WORDS and len(t) > 1]
    
    if not key_tokens:
        return 1.0
        
    grounded_count = sum(1 for token in key_tokens if token in context_text)
    return grounded_count / len(key_tokens)


def batch_faithfulness_metric(records: list[dict]) -> float:
    """Aggregated faithfulness index for the entire dataset without LLM-as-judge."""
    eval_records = [r for r in records if r.get("category") in ["happy_path", "edge"]]
    if not eval_records:
        return 1.0
    scores = [
        compute_non_llm_faithfulness(r.get("output", ""), r.get("sources", []), r.get("category", ""))
        for r in eval_records
    ]
    return sum(scores) / len(scores)


# METRIC 3: Language Compliance Score (Language Drift Control / Risk R-04)

def compute_language_compliance(input_text: str, output_text: str) -> float:
    """
    Evaluates whether the response language matches the user's query language.
    Returns 1.0 (compliance) or 0.0 (language drift / cross-lingual mismatch).
    """
    if not input_text or not output_text:
        return 0.0
        
    cyrillic_pattern = re.compile(r'[\u0400-\u04FF]')
    input_is_ua = bool(cyrillic_pattern.search(input_text))
    output_has_ua = bool(cyrillic_pattern.search(output_text))
    
    if input_is_ua:
        return 1.0 if output_has_ua else 0.0
    else:
        return 1.0 if not output_has_ua else 0.0


def batch_language_compliance_metric(records: list[dict]) -> float:
    """Aggregated business metric for language compliance across the entire dataset."""
    if not records:
        return 1.0
    scores = [compute_language_compliance(r.get("input", ""), r.get("output", "")) for r in records]
    return sum(scores) / len(scores)


# METRIC 4: Safe Refusal & Anti-Hallucination (Safe Refusal / Risk R-03)

def evaluate_safe_refusal_strictness(record: dict) -> float:
    """
    Detailed analysis of refusal quality for Negative/Out-of-Domain queries.
    Returns a value on a scale of [0, 1].
    """
    if record.get("category") != "negative":
        return 1.0
        
    output_text = record.get("output", "").lower()
    
    strict_refusal_keywords = [
        "don't have", "don't know", "does not provide", "not mentioned", 
        "i am sorry", "i'm sorry", "sorry", "unfortunately", "no information",
        "не знаю", "немає в базі", "не володію", "не можу вказати", "не надає",
        "вибачте", "на жаль", "немає інформації", "відсутня інформація"
    ]
    
    has_refusal = any(keyword in output_text for keyword in strict_refusal_keywords)
    if not has_refusal:
        return 0.0
        
    if len(output_text.split()) > 40:
        return 0.5
        
    return 1.0


def batch_safe_refusal_metric(records: list[dict]) -> float:
    """Aggregated index of refusal reliability for negative scope of queries."""
    negative_cases = [r for r in records if r.get("category") == "negative"]
    if not negative_cases:
        return 1.0
    scores = [evaluate_safe_refusal_strictness(r) for r in negative_cases]
    return sum(scores) / len(scores)

