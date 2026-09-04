"""
Adapter over the RAG System Under Test (SUT).

Provides a unified `generate(case)` method to invoke the RAG assistant
and construct a response object containing 'output' and 'sources' fields.
"""

from __future__ import annotations

from rag_sut import RagSUT


class StudentSUT:

  def __init__(self) -> None:
    self._rag = RagSUT()

  def generate(self, case: dict) -> dict:
    """Returns a dict with 'output' (LLM response) and 'sources' (retrieved documents) fields."""
    result = self._rag.ask(case["input"])
    return {"output": result["answer"], "sources": result["sources"]}