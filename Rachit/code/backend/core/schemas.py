from enum import Enum
from typing import List, Optional, Dict
from pydantic import BaseModel, Field


class ContentType(str, Enum):
    text = "text"
    table = "table"
    chart = "chart"
    image = "image"
    ocr = "ocr"

class EvidenceChunk(BaseModel):
    chunk_id: str
    file_id: str
    storage_id: str = ""
    file_hash: Optional[str] = None
    page: int
    content_type: ContentType
    region_id: str
    bbox: List[float] = Field(min_length=4, max_length=4)
    thumbnail_path: Optional[str] = None
    text: str
    ocr_confidence: Optional[float] = None

class RetrievedChunk(BaseModel):
    chunk: EvidenceChunk
    dense_score: Optional[float] = None
    bm25_score: Optional[float] = None
    rerank_score: Optional[float] = None

class Citation(BaseModel):
    source_id: str
    file_id: str
    page: int
    region_id: str
    bbox: List[float]
    thumbnail_path: Optional[str] = None
    text: Optional[str] = None
    filename: Optional[str] = None

class ConfidenceBreakdown(BaseModel):
    level: str  # High/Medium/Low
    score: float
    rerank: float
    hybrid_agreement: float
    citation_faithfulness: float
    extraction_quality: float

class LatencyBreakdown(BaseModel):
    retrieve_ms: float
    rerank_ms: float
    generate_ms: float
    verify_ms: float
    total_ms: float

class AskRequest(BaseModel):
    question: str
    k: int = 5
    file_ids: Optional[List[str]] = None

class AskResponse(BaseModel):
    answer: str
    citations: List[Citation]
    confidence: ConfidenceBreakdown
    refused: bool
    refusal_message: Optional[str] = None
    latency: LatencyBreakdown
    highlighted_page_url: Optional[str] = None

class BatchDecisionRequest(BaseModel):
    file_ids: List[str]
    questions: List[str]

class BatchDecisionResponse(BaseModel):
    # Mapping of question -> (Mapping of file_id -> AskResponse)
    results: Dict[str, Dict[str, AskResponse]]

class CompareResponse(BaseModel):
    keyword_results: List[RetrievedChunk]
    semantic_results: List[RetrievedChunk]

class IngestJob(BaseModel):
    job_id: str
    status: str
    stage: str
    files: List[str]
    chunk_count: int
    region_counts: Optional[Dict[str, int]] = None

class EvalSummary(BaseModel):
    variant: str
    precision_at_5: Optional[float] = None
    recall_at_5: Optional[float] = None
    mrr: Optional[float] = None
    answer_correctness: Optional[float] = None
    faithfulness: Optional[float] = None
    citation_accuracy: Optional[float] = None
    refusal_rate: Optional[float] = None
    p50_ms: Optional[float] = None
    p95_ms: Optional[float] = None
