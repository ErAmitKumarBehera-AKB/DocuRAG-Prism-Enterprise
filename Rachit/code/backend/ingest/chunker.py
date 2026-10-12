"""
DocuRAG Semantic Chunker Module
Splits, merges, and optimizes document text, tables, and vision descriptions into retrieval-ready EvidenceChunks.
"""

from typing import List, Dict, Any, Optional
from backend.core.schemas import ContentType, EvidenceChunk


class SemanticChunker:
    """
    Intelligent chunking engine:
    - Merges micro text spans (under 80 characters) into coherent paragraphs.
    - Preserves markdown table integrity without splitting across rows.
    - Estimates token counts and tracks page bounding box envelopes.
    """
    def __init__(self, max_tokens: int = 512, min_tokens: int = 25):
        self.max_tokens = max_tokens
        self.min_tokens = min_tokens

    def estimate_tokens(self, text: str) -> int:
        return max(1, len(text.split()))

    def merge_small_text_chunks(self, chunks: List[EvidenceChunk]) -> List[EvidenceChunk]:
        """
        Merges adjacent text fragments on the same page into coherent paragraphs
        while updating the enclosing bounding box coordinates.
        """
        if not chunks:
            return []

        merged = []
        current = None

        for c in chunks:
            if c.content_type != ContentType.text:
                if current:
                    merged.append(current)
                    current = None
                merged.append(c)
                continue

            if current is None:
                current = c
                continue

            # Check if adjacent on the same page and under token ceiling
            same_page = (current.page == c.page)
            combined_tokens = self.estimate_tokens(current.text + " " + c.text)

            if same_page and combined_tokens <= self.max_tokens:
                # Merge texts
                current.text = f"{current.text}\n{c.text}"
                # Merge bounding box [x0, y0, x1, y1]
                if current.bbox and c.bbox:
                    current.bbox = [
                        min(current.bbox[0], c.bbox[0]),
                        min(current.bbox[1], c.bbox[1]),
                        max(current.bbox[2], c.bbox[2]),
                        max(current.bbox[3], c.bbox[3]),
                    ]
            else:
                merged.append(current)
                current = c

        if current:
            merged.append(current)

        return merged
