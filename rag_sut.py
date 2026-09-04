"""
Acme Cloud RAG Assistant — System Under Test (SUT).

A lightweight RAG implementation: 
    Query -> e5 Embeddings -> Vector Search (Chroma DB) -> Context Assembly -> Qwen2.5 LLM -> Response.

Interface:
    rag = RagSUT()
    rag.ask("How much storage does the Free plan include?") 
    # Returns: {"answer": str, "sources": ["d1", ...]}
    
    rag.retrieve("...") 
    # Returns: [{"doc_id": "d1", "lang": "en", "text": "..."}, ...]
"""

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Knowledge Base Corpus (Bilingual: EN + UA)
_CORPUS = [
    {"id": "d1", "lang": "en",
     "text": "The Acme Cloud Free plan includes 5 GB of storage and one project."},
    {"id": "d2", "lang": "en",
     "text": "The Acme Cloud Free plan includes 2 GB of storage."},
    {"id": "d3", "lang": "en",
     "text": "The Acme Cloud Pro plan costs 20 US dollars per month and includes 100 GB of storage. "
             "Billing is monthly and can be cancelled at any time from the dashboard."},
    {"id": "d4", "lang": "en",
     "text": "Acme Cloud Pro Plus is a separate, higher tier that costs 40 US dollars per month."},
    {"id": "d5", "lang": "en",
     "text": "You can contact Acme Cloud support at support@acme.example."},
    {"id": "d6", "lang": "en",
     "text": "Acme Cloud stores customer data in EU regions only and is GDPR compliant."},
    {"id": "d7", "lang": "uk",
     "text": "Безкоштовний тариф Acme Cloud надає 5 ГБ сховища та один проєкт."},
    {"id": "d8", "lang": "uk",
     "text": "Тариф Pro коштує 20 доларів США на місяць."},
]

# RAG Pipeline Configuration
_CHUNK_SIZE = 2000
_TOP_K = 2
_EMB_MODEL = "intfloat/multilingual-e5-base"     # Multilingual embedding model
_GEN_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"        # Local generator model


def _load_generator():
    """
    Loads Qwen2.5 model in 4-bit quantization if bitsandbytes is available;
    falls back to standard precision loading otherwise.
    """
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(_GEN_MODEL)
    model_kwargs = {}
    
    # Enable 4-bit quantization if bitsandbytes is available
    try:
        import bitsandbytes  # noqa: F401
        from transformers import BitsAndBytesConfig
        model_kwargs["quantization_config"] = BitsAndBytesConfig(load_in_4bit=True)
    except Exception:
        model_kwargs["torch_dtype"] = "auto"
        
    # Enable automatic device placement if accelerate is available
    try:
        import accelerate  # noqa: F401
        model_kwargs.setdefault("device_map", "auto")  # Uses GPU if available
    except Exception:
        pass
        
    model = AutoModelForCausalLM.from_pretrained(_GEN_MODEL, **model_kwargs)
    return tokenizer, model


class RagSUT:
    """Public interface for the RAG System Under Test."""

    def __init__(self) -> None:
        """Initializes the vector store and loads the local generator LLM."""
        splitter = RecursiveCharacterTextSplitter(chunk_size=_CHUNK_SIZE, chunk_overlap=0)
        docs = []
        for item in _CORPUS:
            for chunk in splitter.split_text(item["text"]):
                docs.append(Document(
                    page_content=chunk,
                    metadata={"doc_id": item["id"], "lang": item["lang"]},
                ))
        self._embeddings = HuggingFaceEmbeddings(
            model_name=_EMB_MODEL, encode_kwargs={"normalize_embeddings": True}
        )
        self._store = Chroma.from_documents(docs, self._embeddings)
        self._tokenizer, self._model = _load_generator()

    def retrieve(self, query: str) -> list[dict]:
        """Performs vector similarity search against the knowledge base."""
        hits = self._store.similarity_search(query, k=_TOP_K)
        return [
            {"doc_id": h.metadata.get("doc_id"),
             "lang": h.metadata.get("lang"),
             "text": h.page_content}
            for h in hits
        ]

    def ask(self, query: str) -> dict:
        """Processes query through RAG pipeline and returns answer with source doc IDs."""
        hits = self.retrieve(query)
        context = "\n".join(h["text"] for h in hits)
        messages = [
            {"role": "system", "content": "Answer the user question using the context."},
            {"role": "user", "content": "Context:\n" + context + "\n\nQuestion: " + query},
        ]
        prompt = self._tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = self._tokenizer(prompt, return_tensors="pt").to(self._model.device)
        output = self._model.generate(**inputs, max_new_tokens=80, do_sample=False)
        answer = self._tokenizer.decode(
            output[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True
        )
        return {"answer": answer, "sources": [h["doc_id"] for h in hits]}