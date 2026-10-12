from typing import List, Protocol, Tuple

from backend.core.schemas import Citation, ConfidenceBreakdown, EvidenceChunk, RetrievedChunk


class Ingestor(Protocol):
    def ingest(self, path: str, original_filename: str, file_id: str, storage_id: str, processing_preference: str = "mixed", pii_mode: str = "STRICT", uploader_role: str = "L1", uploader_name: str = "L1_Analyst", content_hash: str = None) -> List[EvidenceChunk]:
        ...

class Indexer(Protocol):
    def add(self, chunks: List[EvidenceChunk]) -> None:
        ...

class Retriever(Protocol):
    def retrieve(self, query: str, k: int, file_ids: List[str] = None) -> List[RetrievedChunk]:
        ...
    def retrieve_dense(self, query: str, k: int, file_ids: List[str] = None) -> List[RetrievedChunk]:
        ...
    def retrieve_sparse(self, query: str, k: int, file_ids: List[str] = None) -> List[RetrievedChunk]:
        ...

class Reranker(Protocol):
    def rerank(self, query: str, candidates: List[RetrievedChunk]) -> List[RetrievedChunk]:
        ...

class Answerer(Protocol):
    def answer(self, question: str, evidence: List[RetrievedChunk]) -> Tuple[str, List[Citation]]:
        ...

class TrustLayer(Protocol):
    def evaluate(self, question: str, answer: str, citations: List[Citation], evidence: List[RetrievedChunk]) -> Tuple[ConfidenceBreakdown, bool]:
        ...
